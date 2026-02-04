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
from collections import defaultdict
from datetime import datetime, timedelta

import pytz
from dateutil import parser as date_parser
from loguru import logger

from agent.api.state import set_agent_state
from agent.config.constants import TradingConstants, TradingSession
from agent.config.settings import get_settings
from agent.data.indicators import IndicatorCalculator
from agent.data.streaming import BarData, DataStreamer, QuoteData
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
from agent.strategies.base import MarketContext

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

        # Market data cache - stores latest data per symbol
        self._latest_bars: dict[str, BarData] = {}
        self._latest_quotes: dict[str, QuoteData] = {}
        self._daily_bars: dict[str, list[BarData]] = defaultdict(list)

        # Register order update callbacks
        self._setup_order_callbacks()

        # Strategies
        self._strategies = []
        self._init_strategies()

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

        # Track any event for metrics
        self._order_handler.on_any_event(self._on_any_trade_event)

        # Connection monitoring
        self._order_handler.on_disconnect(self._on_stream_disconnect)
        self._order_handler.on_reconnect(self._on_stream_reconnect)

        logger.info("Order update callbacks registered")

    def _on_order_fill(self, update: dict) -> None:
        """Handle order fill events from WebSocket."""
        logger.info(
            f"[FILL] {update['symbol']} - "
            f"Qty: {update.get('filled_qty')} @ ${update.get('filled_avg_price')}"
        )
        # Update metrics
        self._metrics.record_fill(update)

    def _on_partial_fill(self, update: dict) -> None:
        """Handle partial fill events from WebSocket."""
        logger.info(
            f"[PARTIAL FILL] {update['symbol']} - "
            f"Filled: {update.get('filled_qty')}/{update.get('qty')}"
        )

    def _on_order_reject(self, update: dict) -> None:
        """Handle order rejection events from WebSocket."""
        logger.error(
            f"[REJECTED] {update['symbol']} - Order {update['order_id']} - "
            f"Status: {update.get('status')}"
        )
        # Record rejection for analysis
        self._metrics.record_rejection(update)

    def _on_order_cancel(self, update: dict) -> None:
        """Handle order cancellation events from WebSocket."""
        logger.info(f"[CANCELED] {update['symbol']} - Order {update['order_id']}")

    def _on_any_trade_event(self, event: str, update: dict) -> None:
        """Handle any trade event for metrics tracking."""
        self._metrics.record_trade_event(event, update)

    def _on_stream_disconnect(self, error: str) -> None:
        """Handle WebSocket disconnection."""
        logger.warning(f"Trade update stream disconnected: {error}")
        # TODO: Send alert notification

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

        Dynamically collects symbols from each strategy's allowed_symbols parameter.
        Falls back to TIER_1 + TIER_2 assets if no strategies define symbols.
        """
        symbols: set[str] = set()

        for strategy in self._strategies:
            allowed = strategy.parameters.get("allowed_symbols", [])
            symbols.update(allowed)

        # Fallback if no strategies define symbols
        if not symbols:
            symbols = set(TradingConstants.TIER_1_ASSETS + TradingConstants.TIER_2_ASSETS)

        logger.info(f"Trading symbols from {len(self._strategies)} strategies: {sorted(symbols)}")
        return list(symbols)

    def _on_bar_data(self, bar: BarData) -> None:
        """Handle incoming bar data from streaming."""
        self._latest_bars[bar.symbol] = bar
        self._daily_bars[bar.symbol].append(bar)

        # Keep only last 100 bars per symbol to limit memory
        if len(self._daily_bars[bar.symbol]) > 100:
            self._daily_bars[bar.symbol] = self._daily_bars[bar.symbol][-100:]

    def _on_quote_data(self, quote: QuoteData) -> None:
        """Handle incoming quote data from streaming."""
        self._latest_quotes[quote.symbol] = quote

    def _build_market_context(self, symbol: str) -> MarketContext | None:
        """
        Build MarketContext for a symbol from cached data.

        Returns None if insufficient data is available.
        Calculates technical indicators (RSI, MACD, MA50, MA200, ATR) from daily bars.
        """
        bar = self._latest_bars.get(symbol)
        quote = self._latest_quotes.get(symbol)

        if bar is None:
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

        Subscribes to bars and quotes for TIER_1 and TIER_2 assets.
        """
        logger.info("Starting market data streaming...")

        symbols = self._get_trading_symbols()

        # Initialize data streamer
        self._data_streamer = DataStreamer()

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
            self._run_data_streaming(),
            name="data_streaming"
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

        for symbol in symbols:
            context = self._build_market_context(symbol)
            if context is None:
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
                    # TODO: Evaluate exit conditions
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
                    # TODO: Validate with risk manager and execute trade

        if evaluated_count > 0:
            logger.debug(f"Evaluated {evaluated_count} strategy/symbol combinations")

    def _is_symbol_for_strategy(self, symbol: str, strategy) -> bool:
        """
        Check if a symbol is relevant for a given strategy.

        Uses the strategy's allowed_symbols parameter for consistent behavior.
        """
        allowed_symbols = strategy.parameters.get("allowed_symbols", [])
        return symbol in allowed_symbols

    def _on_circuit_breaker_trigger(self, reason: str) -> None:
        """Callback when circuit breaker is triggered."""
        logger.critical(f"CIRCUIT BREAKER TRIGGERED: {reason}")
        # TODO: Send alerts (Slack, email)
        # TODO: Close all positions if severe

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
                    300  # Max 5 minute sleep intervals
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

        logger.info("Daily reset complete")

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

        # Start WebSocket streaming for trade updates
        await self._start_streaming()

        # Start market data streaming
        await self._start_market_data_streaming()

        # Start instrumentation heartbeat for data reception monitoring
        await get_instrumentation().start_heartbeat()

        # Track last logged session to avoid log spam
        last_session = None
        last_can_trade = None

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

                        # Evaluate strategies against current market data
                        # This will:
                        # 1. Build MarketContext from streaming data
                        # 2. Call strategy.evaluate_entry() for each symbol
                        # 3. Record all evaluations via instrumentation
                        # 4. Generate signals for valid entry conditions
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
    logger.info("-" * 60)
    logger.info("24/5 Trading Configuration:")
    logger.info(f"  Extended Hours (4AM-8PM ET): {settings.enable_extended_hours}")
    logger.info(f"  Overnight Trading (8PM-4AM ET): {settings.enable_overnight_trading}")
    logger.info("  Trading Window: Sunday 8 PM ET - Friday 8 PM ET")
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
