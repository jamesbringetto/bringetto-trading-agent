"""Main entry point for the Bringetto Trading Agent.

24/5 Trading Support:
- Paper trading runs from Sunday 8 PM ET through Friday 8 PM ET continuously
- Trading sessions: Overnight (8PM-4AM), Pre-market (4AM-9:30AM),
  Regular (9:30AM-4PM), After-hours (4PM-8PM)
- Weekend closure: Friday 8 PM ET through Sunday 8 PM ET

WebSocket Streaming:
- Trade updates via Alpaca's WebSocket for real-time order fills
- Market data streaming for real-time quotes and bars
"""

import asyncio
import contextlib
import signal
import sys
import uuid
from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal

import pytz
from dateutil import parser as date_parser
from loguru import logger

from agent.api.state import set_agent_state
from agent.config.constants import (
    DecisionType,
    OrderSide,
    TradingConstants,
    TradingSession,
)
from agent.config.settings import get_settings
from agent.data.connection_manager import get_connection_manager
from agent.data.indicators import IndicatorCalculator
from agent.data.streaming import BarData, DataStreamer, QuoteData
from agent.data.symbol_scanner import SymbolScanner
from agent.database import get_session
from agent.database.repositories import (
    StrategyRepository,
    TradeDecisionRepository,
    TradeRepository,
)
from agent.execution.broker import AlpacaBroker, OrderUpdateHandler
from agent.monitoring.instrumentation import get_instrumentation
from agent.monitoring.logger import setup_logging
from agent.monitoring.metrics import MetricsCollector
from agent.risk.circuit_breaker import CircuitBreaker
from agent.risk.validator import TradeValidator
from agent.strategies import (
    EODReversal,
    GapAndGo,
    MomentumScalp,
    OpeningRangeBreakout,
    VWAPReversion,
)
from agent.strategies.base import BaseStrategy, MarketContext, StrategySignal

# How many seconds before market open to switch to 1-second checks
PRE_MARKET_READY_SECONDS = 5

# Weekend closure times (in Eastern Time)
# Trading closes Friday 8 PM ET and reopens Sunday 8 PM ET
WEEKEND_CLOSE_DAY = 4  # Friday
WEEKEND_CLOSE_HOUR = 20  # 8 PM
WEEKEND_OPEN_DAY = 6  # Sunday
WEEKEND_OPEN_HOUR = 20  # 8 PM


class TradingAgent:
    """
    Main trading agent that orchestrates all components.

    Responsibilities:
    - Initialize and manage strategies
    - Process market data
    - Execute trades
    - Monitor risk
    - Track performance
    """

    def __init__(self):
        self._settings = get_settings()
        self._et_tz = pytz.timezone("America/New_York")

        # Core components
        self._broker = AlpacaBroker()
        self._circuit_breaker = CircuitBreaker(on_trigger=self._on_circuit_breaker_trigger)
        self._validator = TradeValidator()
        self._metrics = MetricsCollector()

        # WebSocket streaming handlers
        self._order_handler = OrderUpdateHandler()
        self._data_streamer: DataStreamer | None = None
        self._streaming_task: asyncio.Task | None = None
        self._data_streaming_task: asyncio.Task | None = None

        # Dynamic symbol scanner
        self._scanner: SymbolScanner | None = None
        self._scanned_symbols: list[str] = []
        self._last_rescan_time: datetime | None = None

        # Market data cache - stores latest data per symbol
        self._latest_bars: dict[str, BarData] = {}
        self._latest_quotes: dict[str, QuoteData] = {}
        self._daily_bars: dict[str, list[BarData]] = defaultdict(list)

        # Order-to-trade mapping: broker_order_id -> {trade_id, strategy_name, symbol}
        # Used to correlate WebSocket fill events back to database trades
        self._order_trade_map: dict[str, dict] = {}

        # Strategy name -> database UUID mapping (populated on startup)
        self._strategy_db_ids: dict[str, uuid.UUID] = {}

        # Register order update callbacks
        self._setup_order_callbacks()

        # Strategies
        self._strategies = []
        self._init_strategies()

        # Strategy data feed state
        self._premarket_gaps_scanned_today = False

        # State
        self._is_running = False
        self._shutdown_event = asyncio.Event()

        # Set agent state for API
        set_agent_state("broker", self._broker)
        set_agent_state("circuit_breaker", self._circuit_breaker)
        set_agent_state("strategies", self._strategies)
        set_agent_state("order_handler", self._order_handler)

        logger.info(
            f"TradingAgent initialized - "
            f"Environment: {self._settings.environment}, "
            f"Capital: ${self._settings.paper_trading_capital:,.2f}"
        )

    def _setup_order_callbacks(self) -> None:
        """Set up callbacks for WebSocket trade updates."""
        # Log all fills for tracking
        self._order_handler.on_fill(self._on_order_fill)
        self._order_handler.on_partial_fill(self._on_partial_fill)
        self._order_handler.on_reject(self._on_order_reject)
        self._order_handler.on_cancel(self._on_order_cancel)
        self._order_handler.on_expired(self._on_order_expired)

        # Track any event for metrics
        self._order_handler.on_any_event(self._on_any_trade_event)

        # Connection monitoring
        self._order_handler.on_disconnect(self._on_stream_disconnect)
        self._order_handler.on_reconnect(self._on_stream_reconnect)

        logger.info("Order update callbacks registered")

    def _on_order_fill(self, update: dict) -> None:
        """Handle order fill events from WebSocket.

        This is the critical callback that closes the trade lifecycle:
        - For entry fills: updates trade record with actual fill price
        - For exit fills (stop loss / take profit): closes trade with P&L,
          removes strategy position, feeds circuit breaker
        """
        order_id = update.get("order_id")
        symbol = update.get("symbol")
        filled_price = update.get("filled_avg_price")
        filled_qty = update.get("filled_qty")
        side = update.get("side")

        logger.info(
            f"[FILL] {symbol} - "
            f"Qty: {filled_qty} @ ${filled_price} | "
            f"Side: {side} | Order: {order_id}"
        )

        # Record in metrics
        self._metrics.record_fill(update)

        # Check if this is an exit order (stop loss or take profit leg of a bracket)
        # Exit orders have the opposite side from the entry
        trade_info = self._order_trade_map.get(order_id)
        if trade_info:
            # This is an entry order we tracked - update the trade with fill price
            self._handle_entry_fill(trade_info, update)
            return

        # Check if this fill closes an existing position by looking at strategy positions
        # For bracket orders, the stop/take-profit legs have different order IDs
        # So we match by symbol + opposite side
        self._handle_potential_exit_fill(update)

    def _handle_entry_fill(self, trade_info: dict, update: dict) -> None:
        """Handle fill of an entry order - update trade with actual fill price."""
        filled_price = update.get("filled_avg_price")
        if filled_price is None:
            return

        trade_id = trade_info.get("trade_id")
        strategy_name = trade_info.get("strategy_name")
        if not trade_id:
            return

        # Record entry fill in funnel
        get_instrumentation().record_pipeline_event("orders_filled", strategy_name)

        try:
            with get_session() as session:
                repo = TradeRepository(session)
                trade = repo.get_by_id(trade_id)
                if trade:
                    trade.entry_price = Decimal(str(filled_price))
                    session.flush()
                    logger.info(f"Updated trade {trade_id} entry price to ${filled_price}")
        except Exception as e:
            logger.error(f"Failed to update entry fill in database: {e}")

    def _handle_potential_exit_fill(self, update: dict) -> None:
        """Handle a fill that may be closing an existing position (stop/take-profit).

        Matches by symbol across all strategies to find and close the trade.
        """
        symbol = update.get("symbol")
        filled_price = update.get("filled_avg_price")
        side = update.get("side")

        if not symbol or filled_price is None or not side:
            return

        # Find the strategy that has this position
        for strategy in self._strategies:
            if not strategy.has_position(symbol):
                continue

            position_data = strategy._open_positions.get(symbol)
            if not position_data:
                continue

            entry_side = position_data.get("side")
            # Exit fills are the opposite side of entry
            # Buy entry -> Sell exit, Sell entry -> Buy exit
            if entry_side == "buy" and side != "sell":
                continue
            if entry_side == "sell" and side != "buy":
                continue

            # This fill is closing our position
            entry_price = Decimal(str(position_data.get("entry_price", 0)))
            exit_price = Decimal(str(filled_price))
            qty = position_data.get("qty", 0)

            # Calculate P&L
            if entry_side == "buy":
                pnl = (exit_price - entry_price) * qty
            else:
                pnl = (entry_price - exit_price) * qty

            pnl_pct = (
                (float(pnl) / (float(entry_price) * qty) * 100)
                if entry_price > 0 and qty > 0
                else 0
            )

            logger.info(
                f"[TRADE CLOSED] {symbol} | Strategy: {strategy.name} | "
                f"Entry: ${entry_price} -> Exit: ${exit_price} | "
                f"P&L: ${pnl:.2f} ({pnl_pct:.2f}%)"
            )

            # Record funnel events for trade close
            inst = get_instrumentation()
            inst.record_pipeline_event("trades_closed", strategy.name)
            if pnl > 0:
                inst.record_pipeline_event("trades_won", strategy.name)
            else:
                inst.record_pipeline_event("trades_lost", strategy.name)

            # 1. Close the trade in the database
            trade_id = position_data.get("trade_id")
            if trade_id:
                try:
                    with get_session() as session:
                        repo = TradeRepository(session)
                        repo.close_trade(
                            trade_id=trade_id,
                            exit_price=exit_price,
                            pnl=pnl,
                            pnl_percent=Decimal(str(round(pnl_pct, 2))),
                        )
                    logger.debug(f"Trade {trade_id} closed in database")
                except Exception as e:
                    logger.error(f"Failed to close trade in database: {e}")

            # 2. Record in metrics collector
            self._metrics.record_trade(
                strategy_name=strategy.name,
                pnl=pnl,
                hold_time_seconds=0,  # Will be calculated from DB timestamps
                trade_data={
                    "symbol": symbol,
                    "entry_price": float(entry_price),
                    "exit_price": float(exit_price),
                    "qty": qty,
                    "side": entry_side,
                },
            )

            # 3. Feed circuit breaker with P&L
            self._circuit_breaker.record_trade(pnl, strategy.name)

            # 4. Remove position from strategy tracking
            strategy.remove_position(symbol)

            # 5. Clean up order-trade map
            order_id = position_data.get("order_id")
            if order_id:
                self._order_trade_map.pop(order_id, None)

            # Only handle first matching strategy
            break

    def _on_partial_fill(self, update: dict) -> None:
        """Handle partial fill events from WebSocket."""
        logger.info(
            f"[PARTIAL FILL] {update['symbol']} - "
            f"Filled: {update.get('filled_qty')}/{update.get('qty')}"
        )

    def _on_order_reject(self, update: dict) -> None:
        """Handle order rejection events from WebSocket."""
        order_id = update.get("order_id")
        symbol = update.get("symbol")
        logger.error(f"[REJECTED] {symbol} - Order {order_id} - Status: {update.get('status')}")
        # Record rejection for analysis
        self._metrics.record_rejection(update)

        # If this was a tracked entry order, clean up
        trade_info = self._order_trade_map.pop(order_id, None)
        if trade_info:
            strategy_name = trade_info.get("strategy_name")
            for strategy in self._strategies:
                if strategy.name == strategy_name:
                    strategy.remove_position(symbol)
                    break

    def _on_order_cancel(self, update: dict) -> None:
        """Handle order cancellation events from WebSocket."""
        order_id = update.get("order_id")
        symbol = update.get("symbol")
        logger.info(f"[CANCELED] {symbol} - Order {order_id}")

        # Clean up if tracked entry
        trade_info = self._order_trade_map.pop(order_id, None)
        if trade_info:
            strategy_name = trade_info.get("strategy_name")
            for strategy in self._strategies:
                if strategy.name == strategy_name:
                    strategy.remove_position(symbol)
                    break

    def _on_order_expired(self, update: dict) -> None:
        """Handle order expiration events from WebSocket.

        For bracket orders with DAY TIF, the stop/take-profit legs expire
        at market close. We need to handle this to avoid unprotected positions.
        """
        order_id = update.get("order_id")
        symbol = update.get("symbol")
        logger.warning(f"[EXPIRED] {symbol} - Order {order_id}")

        # Clean up if tracked entry
        self._order_trade_map.pop(order_id, None)

    def _on_any_trade_event(self, event: str, update: dict) -> None:
        """Handle any trade event for metrics tracking."""
        self._metrics.record_trade_event(event, update)

    def _on_stream_disconnect(self, error: str) -> None:
        """Handle WebSocket disconnection."""
        logger.warning(f"Trade update stream disconnected: {error}")

    def _on_stream_reconnect(self) -> None:
        """Handle WebSocket reconnection."""
        logger.info("Trade update stream reconnected")

    def _init_strategies(self) -> None:
        """Initialize all trading strategies."""
        settings = self._settings

        if settings.enable_orb:
            self._strategies.append(OpeningRangeBreakout())
            logger.info("Strategy enabled: Opening Range Breakout")

        if settings.enable_vwap_reversion:
            self._strategies.append(VWAPReversion())
            logger.info("Strategy enabled: VWAP Reversion")

        if settings.enable_momentum_scalp:
            self._strategies.append(MomentumScalp())
            logger.info("Strategy enabled: Momentum Scalp")

        if settings.enable_gap_and_go:
            self._strategies.append(GapAndGo())
            logger.info("Strategy enabled: Gap and Go")

        if settings.enable_eod_reversal:
            self._strategies.append(EODReversal())
            logger.info("Strategy enabled: EOD Reversal")

        logger.info(f"Initialized {len(self._strategies)} strategies")

    def _get_trading_symbols(self) -> list[str]:
        """
        Get all symbols that strategies want to trade.

        Uses scanner results if available. Collects from each strategy's
        allowed_symbols parameter. Falls back to TIER_1 + TIER_2 assets
        if no strategies define symbols and no scan has run.
        """
        symbols: set[str] = set()

        for strategy in self._strategies:
            allowed = strategy.parameters.get("allowed_symbols", [])
            symbols.update(allowed)

        # Fallback if no strategies define symbols (scanner hasn't run yet)
        if not symbols:
            symbols = set(TradingConstants.TIER_1_ASSETS + TradingConstants.TIER_2_ASSETS)

        logger.debug(f"Trading {len(symbols)} symbols from {len(self._strategies)} strategies")
        return list(symbols)

    def _on_bar_data(self, bar: BarData) -> None:
        """Handle incoming bar data from streaming."""
        self._latest_bars[bar.symbol] = bar
        self._daily_bars[bar.symbol].append(bar)

        # Keep only last 100 bars per symbol to limit memory
        if len(self._daily_bars[bar.symbol]) > 100:
            self._daily_bars[bar.symbol] = self._daily_bars[bar.symbol][-100:]

        # Feed bar data to ORB strategy for opening range collection (9:30-9:45 AM ET)
        self._feed_opening_range_data(bar)

        # Feed post-open price action to Gap and Go strategy for pullback detection
        self._feed_gap_price_action(bar)

    def _on_quote_data(self, quote: QuoteData) -> None:
        """Handle incoming quote data from streaming."""
        self._latest_quotes[quote.symbol] = quote

    def _feed_opening_range_data(self, bar: BarData) -> None:
        """Feed bar data to ORB strategy during the opening range window (9:30-9:45 AM ET).

        During the opening range collection window, forwards bar high/low to the
        ORB strategy's update_opening_range() so it can accumulate the range.
        This method is idempotent — safe to call on every bar.
        """
        now = self._get_market_time()
        current_time = now.time()

        # Only during range collection window (9:30-9:45 AM ET)
        range_start = time(9, 30)
        range_end = time(9, 45)
        if not (range_start <= current_time < range_end):
            return

        for strategy in self._strategies:
            if isinstance(strategy, OpeningRangeBreakout) and strategy.is_active:
                if bar.symbol in strategy.parameters.get("allowed_symbols", []):
                    strategy.update_opening_range(
                        symbol=bar.symbol,
                        high=bar.high,
                        low=bar.low,
                    )
                break

    def _feed_gap_price_action(self, bar: BarData) -> None:
        """Feed post-open price action to Gap and Go strategy.

        After market open, the Gap and Go strategy needs to track the day's
        high/low for each symbol to detect pullback entries. This method
        forwards bar data to update_price_action(). Idempotent.
        """
        now = self._get_market_time()
        current_time = now.time()

        # Only after market open (9:30 AM ET)
        if current_time < time(9, 30):
            return

        for strategy in self._strategies:
            if isinstance(strategy, GapAndGo) and strategy.is_active:
                # Only feed price action for symbols in the universe with registered gaps
                if (
                    bar.symbol in strategy.parameters.get("allowed_symbols", [])
                    and strategy.get_gap(bar.symbol) is not None
                ):
                    strategy.update_price_action(
                        symbol=bar.symbol,
                        high=bar.high,
                        low=bar.low,
                    )
                break

    async def _scan_premarket_gaps(self) -> None:
        """Scan for pre-market gaps before market open.

        Fetches previous day's closing prices and current pre-market quotes
        for all symbols in Gap and Go's universe. Registers any gaps >= min_gap_pct.

        This method is idempotent — calling it multiple times on the same day
        will just overwrite gap registrations with updated data.
        """
        gap_strategy = None
        for strategy in self._strategies:
            if isinstance(strategy, GapAndGo) and strategy.is_active:
                gap_strategy = strategy
                break

        if not gap_strategy:
            return

        symbols = gap_strategy.parameters.get("allowed_symbols", [])
        if not symbols:
            logger.warning("Gap and Go has no allowed_symbols — skipping pre-market scan")
            return

        min_gap_pct = gap_strategy.parameters.get("min_gap_pct", 3.0)
        registered_count = 0

        logger.info(f"Scanning {len(symbols)} symbols for pre-market gaps (min {min_gap_pct}%)...")

        for symbol in symbols:
            try:
                # Try snapshot first — gives previous close, current quote, and volume
                snapshot = self._broker.get_snapshot(symbol)
                prev_close = None
                premarket_price = None
                premarket_volume = 0

                if snapshot:
                    prev_close = snapshot.get("previous_close")
                    premarket_volume = snapshot.get("daily_volume", 0) or 0
                    # Use latest trade price or ask from snapshot
                    if snapshot.get("ask") and snapshot["ask"] > 0:
                        premarket_price = Decimal(str(snapshot["ask"]))
                    elif snapshot.get("latest_price") and snapshot["latest_price"] > 0:
                        premarket_price = Decimal(str(snapshot["latest_price"]))

                # Fall back to historical bars for previous close
                if prev_close is None:
                    prev_close = self._broker.get_previous_close(symbol)

                if prev_close is None:
                    continue

                # Fall back to streaming quotes or API for current price
                if premarket_price is None:
                    quote = self._latest_quotes.get(symbol)
                    if quote and quote.ask and quote.ask > 0:
                        premarket_price = quote.ask
                    else:
                        api_quote = self._broker.get_latest_quote(symbol)
                        if api_quote and api_quote.get("ask") and api_quote["ask"] > 0:
                            premarket_price = Decimal(str(api_quote["ask"]))

                if premarket_price is None or premarket_price <= 0:
                    continue

                gap_pct = abs(float(premarket_price - prev_close) / float(prev_close) * 100)

                if gap_pct >= min_gap_pct:
                    result = gap_strategy.register_gap(
                        symbol=symbol,
                        previous_close=prev_close,
                        premarket_price=premarket_price,
                        premarket_volume=premarket_volume,
                    )
                    if result is not None:
                        registered_count += 1

            except Exception as e:
                logger.warning(f"Error scanning gap for {symbol}: {e}")

        self._premarket_gaps_scanned_today = True
        logger.info(
            f"Pre-market gap scan complete: {registered_count} gaps registered "
            f"from {len(symbols)} symbols"
        )

    def _build_market_context(self, symbol: str) -> MarketContext | None:
        """
        Build MarketContext for a symbol from cached data.

        Returns None if insufficient data is available or data is stale.
        Calculates technical indicators (RSI, MACD, MA50, MA200, ATR) from daily bars.
        """
        bar = self._latest_bars.get(symbol)
        quote = self._latest_quotes.get(symbol)

        if bar is None:
            return None

        # Skip stale data - don't evaluate on prices older than 2 minutes
        max_staleness_seconds = 120
        bar_age = (datetime.now(bar.timestamp.tzinfo) - bar.timestamp).total_seconds()
        if bar_age > max_staleness_seconds:
            return None

        # Calculate OHLC from daily bars if available
        daily_bars = self._daily_bars.get(symbol, [])
        if daily_bars:
            open_price = daily_bars[0].open
            high_price = max(b.high for b in daily_bars)
            low_price = min(b.low for b in daily_bars)
            total_volume = sum(b.volume for b in daily_bars)
        else:
            open_price = bar.open
            high_price = bar.high
            low_price = bar.low
            total_volume = bar.volume

        # Calculate technical indicators from daily bars
        indicators = IndicatorCalculator.calculate_all(daily_bars)

        return MarketContext(
            symbol=symbol,
            current_price=bar.close,
            open_price=open_price,
            high_price=high_price,
            low_price=low_price,
            volume=total_volume,
            vwap=bar.vwap,
            bid=quote.bid if quote else None,
            ask=quote.ask if quote else None,
            timestamp=bar.timestamp,
            # Technical indicators
            rsi=indicators["rsi"],
            macd=indicators["macd"],
            macd_signal=indicators["macd_signal"],
            ma_50=indicators["ma_50"],
            ma_200=indicators["ma_200"],
            atr=indicators["atr"],
            adx=indicators["adx"],
        )

    async def _start_market_data_streaming(self) -> None:
        """
        Start market data streaming for all trading symbols.

        Subscribes to bars and quotes for the trading universe.  The DataStreamer
        enforces per-feed subscription caps internally (SIP: 1500, IEX: 500).
        """
        logger.info("Starting market data streaming...")

        symbols = self._get_trading_symbols()

        # Initialize data streamer (reads feed from settings: SIP or IEX)
        self._data_streamer = DataStreamer()

        # Warn if symbol count exceeds the streamer's cap
        if len(symbols) > self._data_streamer._max_subscribed:
            logger.warning(
                f"Trading universe ({len(symbols)} symbols) exceeds "
                f"{self._data_streamer._feed.value.upper()} streaming cap "
                f"({self._data_streamer._max_subscribed}). "
                f"Excess symbols will be dropped by the streamer."
            )

        # Register callbacks
        self._data_streamer.on_bar(self._on_bar_data)
        self._data_streamer.on_quote(self._on_quote_data)

        # Register disconnect/reconnect handlers
        self._data_streamer.on_disconnect(self._on_data_stream_disconnect)
        self._data_streamer.on_reconnect(self._on_data_stream_reconnect)

        # Subscribe to data
        await self._data_streamer.subscribe_bars(symbols)
        await self._data_streamer.subscribe_quotes(symbols)

        # Start streaming in background task with error handling
        self._data_streaming_task = asyncio.create_task(
            self._run_data_streaming(), name="data_streaming"
        )

        logger.info(f"Market data streaming started for {len(symbols)} symbols")

    async def _run_data_streaming(self) -> None:
        """Run data streaming with error logging."""
        try:
            await self._data_streamer.start(auto_reconnect=True)
        except Exception as e:
            logger.error(f"Data streaming task failed: {e}")
            raise

    def _on_data_stream_disconnect(self, error: str) -> None:
        """Handle market data stream disconnection."""
        logger.warning(f"Market data stream disconnected: {error}")

    def _on_data_stream_reconnect(self) -> None:
        """Handle market data stream reconnection."""
        logger.info("Market data stream reconnected")

    async def _stop_market_data_streaming(self) -> None:
        """Stop market data streaming."""
        if self._data_streamer:
            await self._data_streamer.stop()

        if self._data_streaming_task and not self._data_streaming_task.done():
            self._data_streaming_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._data_streaming_task

        logger.info("Market data streaming stopped")

    async def _evaluate_strategies(self) -> None:
        """
        Evaluate all strategies against current market data.

        For each symbol with market data:
        1. Build MarketContext
        2. Call strategy.evaluate_entry() for applicable strategies
        3. Process any generated signals
        """
        symbols = self._get_trading_symbols()
        evaluated_count = 0
        inst = get_instrumentation()

        for symbol in symbols:
            context = self._build_market_context(symbol)
            if context is None:
                # Record skipped evaluation due to missing/stale data (aggregate only)
                inst.record_pipeline_event("skipped_no_data")
                continue

            # Evaluate each active strategy
            for strategy in self._strategies:
                if not strategy.is_active:
                    continue

                # Check if this symbol is relevant for this strategy
                if not self._is_symbol_for_strategy(symbol, strategy):
                    continue

                # Skip if strategy already has position in this symbol
                if strategy.has_position(symbol):
                    # Evaluate exit conditions for existing positions
                    self._evaluate_exit(symbol, strategy, context)
                    continue

                # Evaluate entry conditions
                signal = strategy.evaluate_entry(context)
                evaluated_count += 1

                if signal:
                    # Signal generated - process it
                    logger.info(
                        f"Signal generated: {strategy.name} | {symbol} | "
                        f"{signal.side.value} @ ${signal.entry_price}"
                    )
                    # Validate and execute the trade
                    self._execute_trade(signal, strategy)

        if evaluated_count > 0:
            logger.debug(f"Evaluated {evaluated_count} strategy/symbol combinations")

    def _is_symbol_for_strategy(self, symbol: str, strategy) -> bool:
        """
        Check if a symbol is relevant for a given strategy.

        Uses the strategy's allowed_symbols parameter for consistent behavior.
        """
        allowed_symbols = strategy.parameters.get("allowed_symbols", [])
        return symbol in allowed_symbols

    def _evaluate_exit(self, symbol: str, strategy: BaseStrategy, context: MarketContext) -> None:
        """Evaluate exit conditions for an open position.

        Calls the strategy's should_exit() method and submits a market sell
        if exit conditions are met.
        """
        position_data = strategy._open_positions.get(symbol)
        if not position_data:
            return

        entry_price = Decimal(str(position_data.get("entry_price", 0)))
        entry_side_str = position_data.get("side", "buy")
        entry_side = OrderSide.BUY if entry_side_str == "buy" else OrderSide.SELL

        should_exit, reason = strategy.should_exit(context, entry_price, entry_side)

        if not should_exit:
            return

        logger.info(f"Exit signal: {strategy.name} | {symbol} | Reason: {reason}")

        # Submit market order to close the position
        exit_side = OrderSide.SELL if entry_side == OrderSide.BUY else OrderSide.BUY
        qty = Decimal(str(position_data.get("qty", 0)))

        if qty <= 0:
            return

        # Cancel any existing bracket legs (stop/take-profit) before closing
        order_id = position_data.get("order_id")
        if order_id:
            try:
                self._broker.cancel_order(order_id)
            except Exception as e:
                logger.warning(f"Could not cancel bracket legs for {symbol}: {e}")

        result = self._broker.submit_market_order(
            symbol=symbol,
            side=exit_side,
            qty=qty,
        )

        if result.success:
            logger.info(
                f"Exit order submitted: {exit_side.value} {qty} {symbol} | Reason: {reason}"
            )
            # Position removal will happen in _handle_potential_exit_fill
            # when the WebSocket fill event arrives
        else:
            logger.error(f"Exit order failed for {symbol}: {result.message}")

    def _execute_trade(self, signal: StrategySignal, strategy: BaseStrategy) -> bool:
        """
        Execute a trade based on a strategy signal.

        Validates the signal, calculates position size, submits a bracket order
        with stop loss and take profit attached, and records the trade in the database.

        Args:
            signal: The trading signal from the strategy
            strategy: The strategy that generated the signal

        Returns:
            True if order was submitted successfully, False otherwise
        """
        # Get account info for validation
        account = self._broker.get_account()
        if not account:
            logger.error("Cannot execute trade - failed to get account info")
            return False

        if not account.can_trade():
            logger.warning(f"Cannot execute trade - account cannot trade: {account.status}")
            return False

        # PDT check before entry - a bracket order exit would be a day trade
        pdt_status = self._broker.check_pdt_status()
        if pdt_status and not pdt_status.can_day_trade:
            logger.warning(f"PDT protection: {pdt_status.reason} - skipping {signal.symbol}")
            get_instrumentation().record_pipeline_event("blocked_pdt", strategy.name)
            return False

        # Get current positions for validation
        positions = self._broker.get_positions()
        current_positions = len(positions)
        current_positions_value = sum(p.market_value for p in positions)

        # Validate the signal
        validation = self._validator.validate_signal(
            signal=signal,
            account_value=account.equity,
            buying_power=account.buying_power,
            current_positions=current_positions,
            current_positions_value=current_positions_value,
            daytrading_buying_power=account.daytrading_buying_power,
            is_pattern_day_trader=account.pattern_day_trader,
        )

        if not validation.is_valid:
            logger.warning(f"Signal validation failed for {signal.symbol}: {validation.reason}")
            get_instrumentation().record_pipeline_event(
                "blocked_risk_validation", strategy.name, validation.failure_code
            )
            return False

        # Log warnings if any
        for warning in validation.warnings:
            logger.warning(f"Trade warning for {signal.symbol}: {warning}")

        # Calculate position size in shares
        position_value = account.equity * Decimal(signal.position_size_pct / 100)
        shares = int(position_value / signal.entry_price)

        if shares < 1:
            logger.warning(
                f"Position size too small for {signal.symbol}: "
                f"${position_value:.2f} / ${signal.entry_price} = {shares} shares"
            )
            get_instrumentation().record_pipeline_event("blocked_position_size", strategy.name)
            return False

        # Generate client_order_id for tracking: strategy_name-uuid (max 48 chars)
        client_order_id = f"{strategy.name[:20]}-{uuid.uuid4().hex[:12]}"

        # Submit bracket order with stop loss and take profit
        logger.info(
            f"Executing trade: {signal.side.value} {shares} {signal.symbol} @ ~${signal.entry_price} | "
            f"SL=${signal.stop_loss} | TP=${signal.take_profit} | "
            f"Strategy={strategy.name}"
        )

        result = self._broker.submit_bracket_order(
            symbol=signal.symbol,
            side=signal.side,
            qty=Decimal(shares),
            take_profit_price=signal.take_profit,
            stop_loss_price=signal.stop_loss,
            entry_type="market",
            client_order_id=client_order_id,
        )

        if result.success:
            logger.info(
                f"Order submitted successfully: {signal.symbol} | "
                f"Order ID: {result.order_id} | Status: {result.status.value}"
            )

            # Record funnel event
            get_instrumentation().record_pipeline_event("orders_submitted", strategy.name)

            # Record trade in database
            trade_id = self._record_trade_to_db(signal, strategy, shares, result.order_id)

            # Mark that strategy has a position in this symbol
            position_data = {
                "order_id": result.order_id,
                "trade_id": trade_id,
                "symbol": signal.symbol,
                "side": signal.side.value,
                "qty": shares,
                "entry_price": float(signal.entry_price),
                "stop_loss": float(signal.stop_loss),
                "take_profit": float(signal.take_profit),
                "strategy": strategy.name,
                "timestamp": datetime.now(self._et_tz).isoformat(),
            }
            strategy.add_position(signal.symbol, position_data)

            # Track order -> trade mapping for fill handling
            self._order_trade_map[result.order_id] = {
                "trade_id": trade_id,
                "strategy_name": strategy.name,
                "symbol": signal.symbol,
            }

            return True
        else:
            logger.error(f"Order submission failed for {signal.symbol}: {result.message}")
            get_instrumentation().record_pipeline_event("orders_failed", strategy.name)
            return False

    def _record_trade_to_db(
        self,
        signal: StrategySignal,
        strategy: BaseStrategy,
        shares: int,
        broker_order_id: str,
    ) -> uuid.UUID | None:
        """Record a new trade to the database.

        Returns the trade UUID or None if recording failed.
        """
        strategy_db_id = self._strategy_db_ids.get(strategy.name)
        if not strategy_db_id:
            logger.warning(f"No DB ID for strategy {strategy.name}, skipping trade record")
            return None

        try:
            with get_session() as session:
                trade_repo = TradeRepository(session)
                trade = trade_repo.create(
                    symbol=signal.symbol,
                    strategy_id=strategy_db_id,
                    side=signal.side,
                    entry_price=signal.entry_price,
                    quantity=Decimal(str(shares)),
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                    broker_order_id=broker_order_id,
                )
                trade_id = trade.id

                # Record the trade decision
                decision_repo = TradeDecisionRepository(session)
                decision_repo.create(
                    decision_type=DecisionType.ENTRY,
                    strategy_name=strategy.name,
                    strategy_version=strategy.parameters.get("version", "1.0.0"),
                    symbol=signal.symbol,
                    price=signal.entry_price,
                    reasoning_text=(
                        f"Entry signal: {signal.side.value} {shares} shares @ ${signal.entry_price} | "
                        f"SL=${signal.stop_loss} TP=${signal.take_profit} | "
                        f"Confidence={signal.confidence:.2f} R:R={signal.risk_reward_ratio:.2f}"
                    ),
                    trade_id=trade_id,
                    confidence_score=Decimal(str(round(signal.confidence, 2))),
                    expected_profit_pct=Decimal(
                        str(
                            round(
                                abs(float(signal.take_profit - signal.entry_price))
                                / float(signal.entry_price)
                                * 100,
                                2,
                            )
                        )
                    ),
                    expected_loss_pct=Decimal(
                        str(
                            round(
                                abs(float(signal.entry_price - signal.stop_loss))
                                / float(signal.entry_price)
                                * 100,
                                2,
                            )
                        )
                    ),
                )

            logger.debug(f"Trade recorded in DB: {trade_id} for {signal.symbol}")
            return trade_id

        except Exception as e:
            logger.error(f"Failed to record trade in database: {e}")
            return None

    def _ensure_strategies_in_db(self) -> None:
        """Ensure all active strategies have records in the database.

        Creates strategy records if they don't exist and populates
        the _strategy_db_ids mapping.
        """
        from agent.config.constants import StrategyType

        # Map strategy class names to StrategyType enum
        strategy_type_map = {
            "Opening Range Breakout": StrategyType.ORB,
            "VWAP Mean Reversion": StrategyType.VWAP_REVERSION,
            "Momentum Scalp": StrategyType.MOMENTUM_SCALP,
            "Gap and Go": StrategyType.GAP_AND_GO,
            "EOD Reversal": StrategyType.EOD_REVERSAL,
        }

        try:
            with get_session() as session:
                repo = StrategyRepository(session)
                for strategy in self._strategies:
                    existing = repo.get_by_name(strategy.name)
                    if existing:
                        self._strategy_db_ids[strategy.name] = existing.id
                        logger.debug(f"Strategy {strategy.name} found in DB: {existing.id}")
                    else:
                        strategy_type = strategy_type_map.get(strategy.name, StrategyType.ORB)
                        new_strategy = repo.create(
                            name=strategy.name,
                            strategy_type=strategy_type,
                            parameters=strategy.parameters,
                        )
                        self._strategy_db_ids[strategy.name] = new_strategy.id
                        logger.info(f"Strategy {strategy.name} created in DB: {new_strategy.id}")

            logger.info(f"Strategy DB IDs: {len(self._strategy_db_ids)} strategies mapped")
        except Exception as e:
            logger.error(f"Failed to ensure strategies in database: {e}")

    def _sync_positions_on_startup(self) -> None:
        """Sync broker positions into strategy tracking on startup.

        This prevents duplicate trades after agent restart by loading
        existing positions from Alpaca and assigning them to the
        appropriate strategy.
        """
        positions = self._broker.get_positions()
        if not positions:
            logger.info("No existing positions to sync on startup")
            return

        logger.info(f"Syncing {len(positions)} existing positions from broker...")

        # Try to match positions to open trades in the database
        try:
            with get_session() as session:
                trade_repo = TradeRepository(session)
                open_trades = trade_repo.get_open_trades()

                # Build symbol -> trade mapping
                trade_by_symbol: dict[str, any] = {}
                for trade in open_trades:
                    trade_by_symbol[trade.symbol] = trade

                for position in positions:
                    symbol = position.symbol
                    trade = trade_by_symbol.get(symbol)

                    if trade:
                        # Find strategy by DB ID
                        strategy_name = None
                        for name, db_id in self._strategy_db_ids.items():
                            if db_id == trade.strategy_id:
                                strategy_name = name
                                break

                        if strategy_name:
                            for strategy in self._strategies:
                                if strategy.name == strategy_name:
                                    position_data = {
                                        "order_id": trade.broker_order_id,
                                        "trade_id": trade.id,
                                        "symbol": symbol,
                                        "side": trade.side.value
                                        if hasattr(trade.side, "value")
                                        else str(trade.side),
                                        "qty": float(trade.quantity),
                                        "entry_price": float(trade.entry_price),
                                        "stop_loss": float(trade.stop_loss),
                                        "take_profit": float(trade.take_profit),
                                        "strategy": strategy_name,
                                        "timestamp": trade.entry_time.isoformat()
                                        if trade.entry_time
                                        else "",
                                    }
                                    strategy.add_position(symbol, position_data)
                                    logger.info(
                                        f"Synced position: {symbol} -> {strategy_name} "
                                        f"({trade.side} {trade.quantity} @ ${trade.entry_price})"
                                    )
                                    break
                    else:
                        # Position exists in broker but not in our DB - log warning
                        logger.warning(
                            f"Position {symbol} found in broker but not in trade database. "
                            f"Qty: {position.qty}, Market value: ${position.market_value}"
                        )

        except Exception as e:
            logger.error(f"Failed to sync positions from database: {e}")
            # Fallback: load positions without DB trade IDs
            for position in positions:
                logger.warning(
                    f"Untracked position: {position.symbol} - "
                    f"Qty: {position.qty}, Value: ${position.market_value}"
                )

    def _close_all_day_trading_positions(self) -> None:
        """Close all open positions before market close for day trading.

        This should be called near end of day to ensure no positions
        are held overnight (per day trading strategy).
        """
        positions = self._broker.get_positions()
        if not positions:
            return

        logger.warning(f"EOD CLEANUP: Closing {len(positions)} positions before market close")

        for position in positions:
            symbol = position.symbol
            qty = abs(position.qty)
            side = OrderSide.SELL if position.qty > 0 else OrderSide.BUY

            logger.info(f"EOD closing: {side.value} {qty} {symbol}")
            try:
                result = self._broker.submit_market_order(
                    symbol=symbol,
                    side=side,
                    qty=Decimal(str(qty)),
                )
                if result.success:
                    logger.info(f"EOD close order submitted: {symbol}")
                else:
                    logger.error(f"EOD close failed for {symbol}: {result.message}")
            except Exception as e:
                logger.error(f"EOD close error for {symbol}: {e}")

    def _on_circuit_breaker_trigger(self, reason: str) -> None:
        """Callback when circuit breaker is triggered."""
        logger.critical(f"CIRCUIT BREAKER TRIGGERED: {reason}")
        # TODO: Send alerts (Slack, email)
        # TODO: Close all positions if severe

    # =========================================================================
    # Dynamic Symbol Scanner Methods
    # =========================================================================

    def _run_symbol_scan(self) -> None:
        """
        Run the dynamic symbol scanner and push results to strategies.

        When the scanner is enabled, this replaces the hardcoded SP500_ASSETS list
        by querying Alpaca for all active US equities and filtering by liquidity.
        Falls back to SP500_ASSETS if the scanner is disabled or fails.
        """
        if not self._settings.enable_symbol_scanner:
            logger.info("Symbol scanner disabled — using SP500_ASSETS fallback")
            self._push_fallback_symbols()
            return

        if self._scanner is None:
            self._scanner = SymbolScanner()

        try:
            result = self._scanner.scan()
            self._scanned_symbols = result.all_qualified

            if not self._scanned_symbols:
                logger.warning("Scanner returned no symbols — using SP500_ASSETS fallback")
                self._push_fallback_symbols()
                return

            # Push scanned symbols to all strategies
            for strategy in self._strategies:
                strategy.parameters["allowed_symbols"] = list(self._scanned_symbols)

            self._last_rescan_time = datetime.now(self._et_tz)

            logger.info(
                f"Symbol scan complete: {len(self._scanned_symbols)} symbols "
                f"pushed to {len(self._strategies)} strategies"
            )

        except Exception as e:
            logger.error(f"Symbol scan failed: {e} — using SP500_ASSETS fallback")
            self._push_fallback_symbols()

    def _push_fallback_symbols(self) -> None:
        """Push the hardcoded SP500_ASSETS to all strategies as a fallback."""
        fallback = list(TradingConstants.SP500_ASSETS)
        for strategy in self._strategies:
            if not strategy.parameters.get("allowed_symbols"):
                strategy.parameters["allowed_symbols"] = fallback
        self._scanned_symbols = fallback
        logger.info(f"Fallback: {len(fallback)} SP500 symbols pushed to strategies")

    def _run_intraday_rescan(self) -> None:
        """
        Run intraday rescans for gap and momentum candidates.

        Discovers new symbols that meet gap/momentum criteria and
        dynamically subscribes to their streaming data. Only adds
        new symbols — never removes existing ones mid-session.
        """
        if not self._settings.enable_symbol_scanner or self._scanner is None:
            return

        if self._scanner.last_scan is None:
            return

        new_symbols: set[str] = set()

        # Scan for pre-market gaps
        try:
            gap_candidates = self._scanner.scan_premarket_gaps(
                min_gap_pct=TradingConstants.GAP_MIN_PCT,
                min_price=10.0,
            )
            gap_symbols = [g["symbol"] for g in gap_candidates]
            new_symbols.update(gap_symbols)

            # Push gap candidates to Gap and Go strategy
            for strategy in self._strategies:
                if strategy.name == "Gap and Go" and strategy.is_active:
                    current = set(strategy.parameters.get("allowed_symbols", []))
                    current.update(gap_symbols)
                    strategy.parameters["allowed_symbols"] = list(current)

        except Exception as e:
            logger.warning(f"Gap rescan failed: {e}")

        # Scan for momentum candidates
        try:
            momentum_candidates = self._scanner.scan_momentum_candidates(
                min_price=10.0,
                min_volume=2_000_000,
            )
            momentum_symbols = [m["symbol"] for m in momentum_candidates]
            new_symbols.update(momentum_symbols)

            # Push momentum candidates to Momentum Scalp strategy
            for strategy in self._strategies:
                if strategy.name == "Momentum Scalp" and strategy.is_active:
                    current = set(strategy.parameters.get("allowed_symbols", []))
                    current.update(momentum_symbols)
                    strategy.parameters["allowed_symbols"] = list(current)

        except Exception as e:
            logger.warning(f"Momentum rescan failed: {e}")

        # Subscribe to streaming data for any newly discovered symbols
        if new_symbols and self._data_streamer:
            existing = set(self._get_trading_symbols())
            truly_new = new_symbols - existing
            if truly_new:
                logger.info(f"Intraday rescan found {len(truly_new)} new symbols to subscribe")
                asyncio.create_task(self._subscribe_new_symbols(list(truly_new)))

        self._last_rescan_time = datetime.now(self._et_tz)

    async def _subscribe_new_symbols(self, symbols: list[str]) -> None:
        """Subscribe to streaming data for newly discovered symbols."""
        if not self._data_streamer:
            return
        try:
            await self._data_streamer.subscribe_bars(symbols)
            await self._data_streamer.subscribe_quotes(symbols)
            logger.info(f"Subscribed to {len(symbols)} new symbols from intraday rescan")
        except Exception as e:
            logger.error(f"Failed to subscribe new symbols: {e}")

    def _should_rescan(self) -> bool:
        """Check if it's time for an intraday rescan."""
        if not self._settings.enable_symbol_scanner:
            return False
        if self._last_rescan_time is None:
            return True
        elapsed = (datetime.now(self._et_tz) - self._last_rescan_time).total_seconds()
        return elapsed >= self._settings.scanner_rescan_interval_minutes * 60

    # =========================================================================
    # 24/5 Trading Methods
    # =========================================================================

    def _is_weekend_closure(self) -> bool:
        """
        Check if we're in the weekend closure period.

        24/5 trading is available from Sunday 8 PM ET through Friday 8 PM ET.
        Weekend closure is from Friday 8 PM ET through Sunday 8 PM ET.

        Returns:
            True if in weekend closure period (no trading available)
        """
        now = self._get_market_time()
        weekday = now.weekday()  # Monday = 0, Sunday = 6
        hour = now.hour

        # Friday after 8 PM ET
        if weekday == WEEKEND_CLOSE_DAY and hour >= WEEKEND_CLOSE_HOUR:
            return True

        # Saturday (all day)
        if weekday == 5:  # Saturday
            return True

        # Sunday before 8 PM ET
        return weekday == WEEKEND_OPEN_DAY and hour < WEEKEND_OPEN_HOUR

    def _get_seconds_until_24_5_open(self) -> float:
        """
        Calculate seconds until 24/5 trading window opens.

        Returns:
            Seconds until Sunday 8 PM ET when trading resumes.
            Returns 0 if already within the trading window.
        """
        if not self._is_weekend_closure():
            return 0

        now = self._get_market_time()
        weekday = now.weekday()

        # Calculate next Sunday 8 PM ET
        if weekday == WEEKEND_CLOSE_DAY:  # Friday
            # Next Sunday is 2 days away
            days_until_sunday = 2
        elif weekday == 5:  # Saturday
            # Next Sunday is 1 day away
            days_until_sunday = 1
        else:  # Sunday
            days_until_sunday = 0

        # Create target datetime (Sunday 8 PM ET)
        target = now.replace(
            hour=WEEKEND_OPEN_HOUR,
            minute=0,
            second=0,
            microsecond=0,
        ) + timedelta(days=days_until_sunday)

        seconds_until_open = (target - now).total_seconds()
        return max(0, seconds_until_open)

    def _get_current_session(self) -> TradingSession:
        """Get the current trading session from the broker."""
        return self._broker.get_current_trading_session()

    def _can_trade_in_session(self) -> tuple[bool, str]:
        """
        Check if trading is allowed in the current session based on settings.

        Considers:
        - Weekend closure (no trading Friday 8 PM - Sunday 8 PM ET)
        - Extended hours settings (pre-market, after-hours)
        - Overnight trading settings
        - Circuit breaker status

        Returns:
            Tuple of (can_trade, reason)
        """
        # Check weekend closure first
        if self._is_weekend_closure():
            return False, "Weekend closure (Friday 8 PM - Sunday 8 PM ET)"

        # Get current session
        session = self._get_current_session()
        settings = self._settings

        # Regular hours always allowed
        if session == TradingSession.REGULAR:
            return True, "Regular market hours"

        # Pre-market and after-hours
        if session in (TradingSession.PRE_MARKET, TradingSession.AFTER_HOURS):
            if settings.enable_extended_hours:
                return True, f"{session.value.replace('_', ' ').title()} session"
            return False, f"{session.value.replace('_', ' ').title()} trading disabled"

        # Overnight session
        if session == TradingSession.OVERNIGHT:
            if settings.enable_overnight_trading:
                return True, "Overnight session (LIMIT orders only)"
            return False, "Overnight trading disabled"

        return False, f"Unknown session: {session}"

    def _get_market_time(self) -> datetime:
        """Get current time in Eastern timezone."""
        return datetime.now(self._et_tz)

    def _is_market_open(self) -> bool:
        """Check if market is open using broker."""
        return self._broker.is_market_open()

    def _get_seconds_until_market_open(self) -> float | None:
        """
        Calculate seconds until market opens.

        Returns:
            Seconds until market open, or None if unable to determine.
            Returns 0 if market is already open.
        """
        try:
            market_hours = self._broker.get_market_hours()
            if not market_hours:
                return None

            if market_hours.get("is_open"):
                return 0

            next_open_str = market_hours.get("next_open")
            if not next_open_str:
                return None

            # Parse the next_open timestamp
            next_open = date_parser.isoparse(next_open_str)
            now = datetime.now(next_open.tzinfo)

            seconds_until_open = (next_open - now).total_seconds()
            return max(0, seconds_until_open)

        except Exception as e:
            logger.error(f"Error calculating time until market open: {e}")
            return None

    async def _wait_for_market_open(self) -> None:
        """
        Efficiently wait for market to open.

        Uses smart sleeping:
        - If >5 seconds until open: sleep until 5 seconds before
        - If <=5 seconds until open: check every 1 second
        - Checks for shutdown during wait
        """
        while not self._shutdown_event.is_set():
            seconds_until_open = self._get_seconds_until_market_open()

            if seconds_until_open is None:
                # Couldn't determine, fall back to checking every 30 seconds
                logger.warning("Unable to determine market open time, checking in 30s")
                await asyncio.sleep(30)
                continue

            if seconds_until_open == 0:
                # Market is open
                return

            if seconds_until_open <= PRE_MARKET_READY_SECONDS:
                # Within ready window, check every second
                logger.debug(f"Market opens in {seconds_until_open:.1f}s - checking every second")
                await asyncio.sleep(1)
            else:
                # Sleep until ready window, but cap at 5 minutes to allow for shutdown checks
                sleep_time = min(
                    seconds_until_open - PRE_MARKET_READY_SECONDS,
                    300,  # Max 5 minute sleep intervals
                )
                hours, remainder = divmod(int(seconds_until_open), 3600)
                minutes, seconds = divmod(remainder, 60)

                if hours > 0:
                    time_str = f"{hours}h {minutes}m {seconds}s"
                elif minutes > 0:
                    time_str = f"{minutes}m {seconds}s"
                else:
                    time_str = f"{seconds}s"

                logger.info(f"Market opens in {time_str} - sleeping for {sleep_time:.0f}s")
                await asyncio.sleep(sleep_time)

    async def _wait_for_24_5_window(self) -> None:
        """
        Wait for the 24/5 trading window to open (Sunday 8 PM ET).

        During weekend closure (Friday 8 PM - Sunday 8 PM ET), this method
        will sleep efficiently until trading resumes.
        """
        while not self._shutdown_event.is_set() and self._is_weekend_closure():
            seconds_until_open = self._get_seconds_until_24_5_open()

            if seconds_until_open == 0:
                return

            # Sleep in chunks (max 5 minutes) to allow shutdown checks
            sleep_time = min(seconds_until_open, 300)

            hours, remainder = divmod(int(seconds_until_open), 3600)
            minutes, seconds = divmod(remainder, 60)

            if hours > 0:
                time_str = f"{hours}h {minutes}m {seconds}s"
            elif minutes > 0:
                time_str = f"{minutes}m {seconds}s"
            else:
                time_str = f"{seconds}s"

            logger.info(f"Weekend closure - 24/5 trading opens in {time_str}")
            await asyncio.sleep(sleep_time)

    async def _check_strategies(self) -> None:
        """Check if any strategies should be auto-disabled."""
        for strategy in self._strategies:
            if not strategy.is_active:
                continue

            if self._metrics.should_disable_strategy(strategy.name):
                strategy.disable("Auto-disabled due to poor performance")
                logger.warning(f"Strategy {strategy.name} auto-disabled")

            if self._circuit_breaker.check_strategy_losses(strategy.name):
                strategy.disable("Too many consecutive losses")
                logger.warning(f"Strategy {strategy.name} disabled - consecutive losses")

    async def _daily_reset(self) -> None:
        """Reset daily state for all components."""
        logger.info("Performing daily reset...")

        for strategy in self._strategies:
            if hasattr(strategy, "reset_daily"):
                strategy.reset_daily()

        # Clear stale order-trade mappings
        self._order_trade_map.clear()

        # Reset pre-market gap scan flag for the new day
        self._premarket_gaps_scanned_today = False

        # Re-run symbol scan for the new trading day
        self._run_symbol_scan()

        logger.info("Daily reset complete")

    def _should_close_eod_positions(self) -> bool:
        """Check if it's time to close all positions for end of day.

        Returns True when within the avoid_last_minutes window before market close.
        """
        now = self._get_market_time()
        close_hour = self._settings.market_close_hour
        close_minute = self._settings.market_close_minute
        avoid_last = self._settings.avoid_last_minutes

        # Calculate the cutoff time
        cutoff_minutes = close_minute - avoid_last
        cutoff_hour = close_hour
        if cutoff_minutes < 0:
            cutoff_hour -= 1
            cutoff_minutes += 60

        cutoff_time = time(cutoff_hour, cutoff_minutes)
        market_close = time(close_hour, close_minute)

        current_time = now.time()
        return cutoff_time <= current_time <= market_close

    async def _start_streaming(self) -> None:
        """
        Start WebSocket streaming for trade updates.

        Per Alpaca documentation:
        - Connects to wss://paper-api.alpaca.markets/stream (paper) or
          wss://api.alpaca.markets/stream (live)
        - Authenticates and subscribes to trade_updates stream
        - Handles automatic reconnection with exponential backoff
        """
        logger.info("Starting WebSocket streaming for trade updates...")

        try:
            # Start the order update handler with auto-reconnection
            self._streaming_task = asyncio.create_task(
                self._order_handler.start_with_reconnect(max_attempts=10)
            )
            logger.info("Trade update WebSocket stream started")
        except Exception as e:
            logger.error(f"Failed to start trade update stream: {e}")

    async def _stop_streaming(self) -> None:
        """Stop WebSocket streaming."""
        logger.info("Stopping WebSocket streaming...")

        try:
            # Stop order update handler
            if self._order_handler.is_running():
                await self._order_handler.stop()

            # Cancel streaming task
            if self._streaming_task and not self._streaming_task.done():
                self._streaming_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._streaming_task

            logger.info("WebSocket streaming stopped")
        except Exception as e:
            logger.error(f"Error stopping streaming: {e}")

    def get_streaming_status(self) -> dict:
        """Get status of WebSocket streams for monitoring."""
        return {
            "order_updates": self._order_handler.get_health_status(),
            "data_stream": self._data_streamer.get_health_status() if self._data_streamer else None,
            "connection_manager": get_connection_manager().get_status(),
        }

    async def run(self) -> None:
        """
        Main run loop for the trading agent.

        Supports 24/5 trading:
        - Active from Sunday 8 PM ET through Friday 8 PM ET
        - Sleeps during weekend closure (Friday 8 PM - Sunday 8 PM ET)
        - Respects extended hours and overnight trading settings

        WebSocket streaming:
        - Starts trade update stream on agent start
        - Receives real-time order fills, cancellations, rejections
        - Auto-reconnects on disconnection
        """
        logger.info("Starting Trading Agent with 24/5 support...")
        self._is_running = True
        set_agent_state("is_running", True)

        # Log 24/5 trading configuration
        logger.info(
            f"24/5 Trading Config - "
            f"Extended hours: {self._settings.enable_extended_hours}, "
            f"Overnight trading: {self._settings.enable_overnight_trading}"
        )

        # Check account status
        account = self._broker.get_account()
        if account:
            logger.info(
                f"Account status - "
                f"Status: {account.status.value}, "
                f"Equity: ${account.equity:,.2f}, "
                f"Cash: ${account.cash:,.2f}, "
                f"Buying power: ${account.buying_power:,.2f}"
            )
            logger.info(
                f"Account permissions - "
                f"Can trade: {account.can_trade()}, "
                f"Can day trade: {account.can_day_trade()}, "
                f"Shorting enabled: {account.shorting_enabled}, "
                f"PDT flag: {account.pattern_day_trader}"
            )

            # Check for account restrictions
            if account.trading_blocked:
                logger.error("TRADING BLOCKED - Account cannot place orders")
                return
            if account.account_blocked:
                logger.error("ACCOUNT BLOCKED - Account is blocked from all activity")
                return
            if account.trade_suspended_by_user:
                logger.warning("Trading suspended by user - will not execute trades")
            if not account.is_active():
                logger.error(f"Account not active - Status: {account.status.value}")
                return
        else:
            logger.error("Failed to get account info - check API credentials")
            return

        # Ensure strategies exist in database and get their IDs
        self._ensure_strategies_in_db()

        # Sync existing positions from broker on startup
        self._sync_positions_on_startup()

        # Run initial symbol scan to discover tradeable universe
        self._run_symbol_scan()

        # Start WebSocket streaming for trade updates
        await self._start_streaming()

        # Stagger the data stream connection to avoid hitting Alpaca's
        # connection limit.  The trading stream connects first; we wait a
        # few seconds before opening the (separate) stock-data stream so
        # both connections don't race for the limit simultaneously.
        logger.info("Waiting 5 s before starting market data stream (stagger connections)...")
        await asyncio.sleep(5)

        # Start market data streaming (uses scanner results)
        await self._start_market_data_streaming()

        # Start instrumentation heartbeat for data reception monitoring
        await get_instrumentation().start_heartbeat()

        # Track last logged session to avoid log spam
        last_session = None
        last_can_trade = None
        eod_closed_today = False

        # Main loop
        try:
            while not self._shutdown_event.is_set():
                try:
                    # Check weekend closure first
                    if self._is_weekend_closure():
                        logger.info("Weekend closure detected - waiting for Sunday 8 PM ET...")
                        await self._wait_for_24_5_window()

                        if self._shutdown_event.is_set():
                            break
                        continue

                    # We're within the 24/5 window (Sunday 8 PM - Friday 8 PM)
                    current_session = self._get_current_session()
                    can_trade_session, session_reason = self._can_trade_in_session()

                    # Log session changes
                    if current_session != last_session:
                        logger.info(f"Session change: {current_session.value} - {session_reason}")
                        last_session = current_session

                    # Log trading availability changes
                    if can_trade_session != last_can_trade:
                        if can_trade_session:
                            logger.info(f"Trading ENABLED: {session_reason}")
                        else:
                            logger.info(f"Trading DISABLED: {session_reason}")
                        last_can_trade = can_trade_session

                    # If we can trade in this session, run the trading loop
                    if can_trade_session:
                        # Check circuit breaker
                        can_trade_cb, cb_reason = self._circuit_breaker.can_trade()
                        if not can_trade_cb:
                            logger.warning(f"Circuit breaker active: {cb_reason}")
                            await asyncio.sleep(60)
                            continue

                        # Check strategies for auto-disable
                        await self._check_strategies()

                        # End-of-day position closure for day trading
                        if (
                            self._settings.trading_mode == "day_trading"
                            and current_session == TradingSession.REGULAR
                            and self._should_close_eod_positions()
                            and not eod_closed_today
                        ):
                            self._close_all_day_trading_positions()
                            eod_closed_today = True
                            await asyncio.sleep(5)
                            continue

                        # Reset EOD flag at start of new day
                        now_et = self._get_market_time()
                        if now_et.hour < 10:
                            eod_closed_today = False

                        # Scan for pre-market gaps once per day before Gap and Go's
                        # trading window (9:35 AM ET). Runs during pre-market or early
                        # regular session to register qualifying gaps.
                        if not self._premarket_gaps_scanned_today:
                            now_et = self._get_market_time()
                            # Scan anytime from pre-market through 9:34 AM ET
                            if now_et.time() < time(9, 35):
                                await self._scan_premarket_gaps()
                            else:
                                # Past the window — mark as done to avoid repeated checks
                                self._premarket_gaps_scanned_today = True
                                logger.info(
                                    "Pre-market gap scan window passed (after 9:35 AM) — "
                                    "skipping for today"
                                )

                        # Run intraday rescan if enough time has passed
                        if self._should_rescan():
                            self._run_intraday_rescan()

                        # Evaluate strategies against current market data
                        # This will:
                        # 1. Build MarketContext from streaming data
                        # 2. Call strategy.evaluate_entry() for each symbol
                        # 3. Evaluate exit conditions for open positions
                        # 4. Record all evaluations via instrumentation
                        # 5. Generate signals for valid entry conditions
                        await self._evaluate_strategies()

                        # Note: During overnight session, only LIMIT orders with
                        # DAY or GTC TIF are supported. Strategies should be aware
                        # of this and adjust their order types accordingly.

                        # Trading loop runs every second during active sessions
                        await asyncio.sleep(1)
                    else:
                        # Can't trade in this session, but stay awake to monitor
                        # Check every 30 seconds for session changes
                        await asyncio.sleep(30)

                except Exception as e:
                    logger.error(f"Error in main loop: {e}")
                    await asyncio.sleep(5)

        except asyncio.CancelledError:
            logger.info("Agent run loop cancelled")
        finally:
            self._is_running = False
            set_agent_state("is_running", False)
            logger.info("Trading Agent stopped")

    async def shutdown(self) -> None:
        """Graceful shutdown of the agent."""
        logger.info("Initiating graceful shutdown...")
        self._shutdown_event.set()

        # Stop instrumentation heartbeat
        await get_instrumentation().stop_heartbeat()

        # Stop market data streaming
        await self._stop_market_data_streaming()

        # Stop WebSocket streaming
        await self._stop_streaming()

        # Give time for current operations to complete
        await asyncio.sleep(2)

        # Close all positions if configured to do so
        # (disabled by default - manual control preferred)
        # await self._broker.close_all_positions()

        logger.info("Shutdown complete")


def handle_signals(agent: TradingAgent, loop: asyncio.AbstractEventLoop) -> None:
    """Set up signal handlers for graceful shutdown."""

    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}")
        asyncio.run_coroutine_threadsafe(agent.shutdown(), loop)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


async def main() -> None:
    """Main entry point."""
    # Setup logging
    setup_logging()

    logger.info("=" * 60)
    logger.info("BRINGETTO TRADING AGENT")
    logger.info("24/5 Trading Enabled")
    logger.info("=" * 60)

    settings = get_settings()
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Trading Mode: {settings.trading_mode}")
    logger.info(f"Paper Trading Capital: ${settings.paper_trading_capital:,.2f}")
    logger.info(f"Data Feed: {settings.alpaca_data_feed.upper()}")
    logger.info("-" * 60)
    logger.info("24/5 Trading Configuration:")
    logger.info(f"  Extended Hours (4AM-8PM ET): {settings.enable_extended_hours}")
    logger.info(f"  Overnight Trading (8PM-4AM ET): {settings.enable_overnight_trading}")
    logger.info("  Trading Window: Sunday 8 PM ET - Friday 8 PM ET")
    logger.info("-" * 60)
    logger.info("Symbol Scanner Configuration:")
    logger.info(f"  Enabled: {settings.enable_symbol_scanner}")
    logger.info(f"  Min Price: ${settings.scanner_min_price}")
    logger.info(f"  Min Avg Volume: {settings.scanner_min_avg_volume:,}")
    logger.info(f"  Max Symbols: {settings.scanner_max_symbols}")
    logger.info(f"  Rescan Interval: {settings.scanner_rescan_interval_minutes} min")
    logger.info("=" * 60)

    # Create and run agent
    agent = TradingAgent()

    # Setup signal handlers
    loop = asyncio.get_event_loop()
    handle_signals(agent, loop)

    try:
        await agent.run()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        await agent.shutdown()
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        await agent.shutdown()
        sys.exit(1)


def run() -> None:
    """Synchronous entry point."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
