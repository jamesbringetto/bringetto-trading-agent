"""Real-time market data streaming via WebSocket.

This module provides real-time market data streaming using Alpaca's WebSocket API.

Compliance Notes:
- Per Alpaca's terms, we must monitor for connectivity issues
- Automatic reconnection is implemented with exponential backoff
- All connection errors are logged for compliance reporting

Connection-Limit Handling:
- Alpaca free/paper tier allows only 1 concurrent connection per stream type.
- When a connection drops, the server-side socket can linger for 60-120+ seconds.
- The SDK's internal ``_run_forever`` retries create additional connections that
  count against the limit, making rapid reconnection counterproductive.
- We use the ``ConnectionManager`` singleton to enforce escalating cooldowns
  (120 s → 240 s → 480 s → …) for "connection limit exceeded" errors, and
  connection-limit failures are NOT counted toward the max-reconnect cap.
"""

import asyncio
import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from alpaca.data.enums import DataFeed
from alpaca.data.live import StockDataStream
from alpaca.data.models import Bar, Quote, Trade
from loguru import logger

from agent.config.settings import get_settings
from agent.data.connection_manager import (
    StreamType,
    get_connection_manager,
)
from agent.monitoring.instrumentation import get_instrumentation

# Reconnection configuration for NON-connection-limit errors.
# Connection-limit backoff is managed by ConnectionManager with much longer
# delays (see agent/data/connection_manager.py).
MAX_RECONNECT_ATTEMPTS = 20  # only counts non-connection-limit failures
INITIAL_RECONNECT_DELAY = 2.0  # seconds
MAX_RECONNECT_DELAY = 60.0  # seconds

# Per-type subscription caps.  SIP (paid, $99/mo) can handle many more symbols
# than the free IEX feed.  These are practical caps to prevent client-side
# overload, not hard Alpaca limits.
MAX_SUBSCRIBED_SYMBOLS_IEX = 500
MAX_SUBSCRIBED_SYMBOLS_SIP = 1500


@dataclass
class BarData:
    """Processed bar data."""

    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    vwap: Decimal | None


@dataclass
class QuoteData:
    """Processed quote data."""

    symbol: str
    timestamp: datetime
    bid: Decimal
    ask: Decimal
    bid_size: int
    ask_size: int


@dataclass
class TradeData:
    """Processed trade data."""

    symbol: str
    timestamp: datetime
    price: Decimal
    size: int


class DataStreamer:
    """
    Real-time market data streaming using Alpaca WebSocket.

    Supports:
    - Bar data (OHLCV)
    - Quote data (bid/ask)
    - Trade data (individual trades)

    Features:
    - Automatic reconnection with exponential backoff
    - Connection health monitoring
    - Configurable data feed (IEX free, SIP paid)
    """

    def __init__(self, feed: DataFeed | None = None):
        """
        Initialize the data streamer.

        Args:
            feed: Data feed to use.  If None (default), reads from
                ``ALPACA_DATA_FEED`` setting (``sip`` or ``iex``).
        """
        settings = get_settings()
        self._api_key = settings.alpaca_api_key
        self._secret_key = settings.alpaca_secret_key

        if feed is None:
            self._feed = DataFeed.SIP if settings.use_sip_feed else DataFeed.IEX
        else:
            self._feed = feed

        # Set subscription cap based on feed tier
        self._max_subscribed = (
            MAX_SUBSCRIBED_SYMBOLS_SIP
            if self._feed == DataFeed.SIP
            else MAX_SUBSCRIBED_SYMBOLS_IEX
        )

        self._stream: StockDataStream | None = None
        self._is_running = False
        self._should_reconnect = True
        self._reconnect_attempts = 0
        self._last_data_time: datetime | None = None

        # Callbacks
        self._bar_callbacks: list[Callable[[BarData], None]] = []
        self._quote_callbacks: list[Callable[[QuoteData], None]] = []
        self._trade_callbacks: list[Callable[[TradeData], None]] = []

        # Disconnect callback for alerting
        self._on_disconnect_callbacks: list[Callable[[str], None]] = []
        self._on_reconnect_callbacks: list[Callable[[], None]] = []

        # Subscribed symbols
        self._subscribed_bars: set[str] = set()
        self._subscribed_quotes: set[str] = set()
        self._subscribed_trades: set[str] = set()

        logger.info(f"DataStreamer initialized with {feed.value} feed")

    def _init_stream(self) -> None:
        """Initialize the data stream."""
        if self._stream is None:
            self._stream = StockDataStream(
                api_key=self._api_key,
                secret_key=self._secret_key,
                feed=self._feed,
            )

    def on_disconnect(self, callback: Callable[[str], None]) -> None:
        """Register a callback for disconnection events."""
        self._on_disconnect_callbacks.append(callback)

    def on_reconnect(self, callback: Callable[[], None]) -> None:
        """Register a callback for successful reconnection."""
        self._on_reconnect_callbacks.append(callback)

    async def _handle_bar(self, bar: Bar) -> None:
        """Handle incoming bar data."""
        self._last_data_time = datetime.now()

        logger.debug(f"Received bar: {bar.symbol} @ {bar.close}")

        # Record data reception for instrumentation
        get_instrumentation().record_bar(bar.symbol)

        bar_data = BarData(
            symbol=bar.symbol,
            timestamp=bar.timestamp,
            open=Decimal(str(bar.open)),
            high=Decimal(str(bar.high)),
            low=Decimal(str(bar.low)),
            close=Decimal(str(bar.close)),
            volume=bar.volume,
            vwap=Decimal(str(bar.vwap)) if bar.vwap else None,
        )

        for callback in self._bar_callbacks:
            try:
                callback(bar_data)
            except Exception as e:
                logger.error(f"Error in bar callback: {e}")

    async def _handle_quote(self, quote: Quote) -> None:
        """Handle incoming quote data."""
        self._last_data_time = datetime.now()

        # Record data reception for instrumentation
        get_instrumentation().record_quote(quote.symbol)

        quote_data = QuoteData(
            symbol=quote.symbol,
            timestamp=quote.timestamp,
            bid=Decimal(str(quote.bid_price)),
            ask=Decimal(str(quote.ask_price)),
            bid_size=quote.bid_size,
            ask_size=quote.ask_size,
        )

        for callback in self._quote_callbacks:
            try:
                callback(quote_data)
            except Exception as e:
                logger.error(f"Error in quote callback: {e}")

    async def _handle_trade(self, trade: Trade) -> None:
        """Handle incoming trade data."""
        self._last_data_time = datetime.now()

        # Record data reception for instrumentation
        get_instrumentation().record_trade_tick(trade.symbol)

        trade_data = TradeData(
            symbol=trade.symbol,
            timestamp=trade.timestamp,
            price=Decimal(str(trade.price)),
            size=trade.size,
        )

        for callback in self._trade_callbacks:
            try:
                callback(trade_data)
            except Exception as e:
                logger.error(f"Error in trade callback: {e}")

    def on_bar(self, callback: Callable[[BarData], None]) -> None:
        """Register a callback for bar data."""
        self._bar_callbacks.append(callback)

    def on_quote(self, callback: Callable[[QuoteData], None]) -> None:
        """Register a callback for quote data."""
        self._quote_callbacks.append(callback)

    def on_trade(self, callback: Callable[[TradeData], None]) -> None:
        """Register a callback for trade data."""
        self._trade_callbacks.append(callback)

    async def subscribe_bars(self, symbols: list[str]) -> None:
        """Subscribe to bar data for symbols (capped at per-feed limit)."""
        self._init_stream()
        if self._stream is None:
            return

        new_symbols = set(symbols) - self._subscribed_bars

        # Enforce subscription cap to avoid stream overload
        remaining_capacity = self._max_subscribed - len(self._subscribed_bars)
        if remaining_capacity <= 0:
            logger.warning(
                f"Bar subscription cap reached ({self._max_subscribed}), "
                f"ignoring {len(new_symbols)} new symbols"
            )
            return

        if len(new_symbols) > remaining_capacity:
            new_symbols = set(list(new_symbols)[:remaining_capacity])
            logger.warning(
                f"Capping new bar subscriptions to {len(new_symbols)} "
                f"(cap: {self._max_subscribed})"
            )

        if new_symbols:
            self._stream.subscribe_bars(self._handle_bar, *new_symbols)
            self._subscribed_bars.update(new_symbols)
            logger.info(
                f"Subscribed to bars: {len(new_symbols)} symbols (total: {len(self._subscribed_bars)})"
            )

    async def subscribe_quotes(self, symbols: list[str]) -> None:
        """Subscribe to quote data for symbols (capped at per-feed limit)."""
        self._init_stream()
        if self._stream is None:
            return

        new_symbols = set(symbols) - self._subscribed_quotes

        # Enforce subscription cap
        remaining_capacity = self._max_subscribed - len(self._subscribed_quotes)
        if remaining_capacity <= 0:
            logger.warning(
                f"Quote subscription cap reached ({self._max_subscribed}), "
                f"ignoring {len(new_symbols)} new symbols"
            )
            return

        if len(new_symbols) > remaining_capacity:
            new_symbols = set(list(new_symbols)[:remaining_capacity])
            logger.warning(
                f"Capping new quote subscriptions to {len(new_symbols)} "
                f"(cap: {self._max_subscribed})"
            )

        if new_symbols:
            self._stream.subscribe_quotes(self._handle_quote, *new_symbols)
            self._subscribed_quotes.update(new_symbols)
            logger.info(
                f"Subscribed to quotes: {len(new_symbols)} symbols (total: {len(self._subscribed_quotes)})"
            )

    async def subscribe_trades(self, symbols: list[str]) -> None:
        """Subscribe to trade data for symbols (capped at per-feed limit)."""
        self._init_stream()
        if self._stream is None:
            return

        new_symbols = set(symbols) - self._subscribed_trades

        # Enforce subscription cap
        remaining_capacity = self._max_subscribed - len(self._subscribed_trades)
        if remaining_capacity <= 0:
            logger.warning(
                f"Trade subscription cap reached ({self._max_subscribed}), "
                f"ignoring {len(new_symbols)} new symbols"
            )
            return

        if len(new_symbols) > remaining_capacity:
            new_symbols = set(list(new_symbols)[:remaining_capacity])
            logger.warning(
                f"Capping new trade subscriptions to {len(new_symbols)} "
                f"(cap: {self._max_subscribed})"
            )

        if new_symbols:
            self._stream.subscribe_trades(self._handle_trade, *new_symbols)
            self._subscribed_trades.update(new_symbols)
            logger.info(
                f"Subscribed to trades: {len(new_symbols)} symbols (total: {len(self._subscribed_trades)})"
            )

    async def start(self, auto_reconnect: bool = True) -> None:
        """
        Start the data stream with automatic reconnection.

        Per Alpaca's terms of service, we must monitor for connectivity issues
        and implement automatic reconnection.

        Connection-limit errors ("connection limit exceeded", HTTP 429) are
        handled specially:
        - They are NOT counted toward ``MAX_RECONNECT_ATTEMPTS`` because they
          are a transient server-side condition that will resolve on its own.
        - The ``ConnectionManager`` singleton enforces escalating cooldowns
          (120 s, 240 s, 480 s, …) so the agent does not hammer the limit.
        - Only non-connection-limit failures increment the retry counter.

        Args:
            auto_reconnect: Whether to automatically reconnect on disconnect
        """
        if self._is_running:
            logger.warning("DataStreamer already running")
            return

        self._should_reconnect = auto_reconnect
        self._reconnect_attempts = 0
        conn_mgr = get_connection_manager()
        is_first_attempt = True

        logger.info(
            f"DataStreamer connecting - Feed: {self._feed.value}, "
            f"Bars: {len(self._subscribed_bars)}, Quotes: {len(self._subscribed_quotes)}"
        )

        while True:
            try:
                # Ask the ConnectionManager for clearance before connecting.
                # This enforces cooldowns after connection-limit errors and
                # serialises connection attempts across stream types.
                await conn_mgr.wait_for_clearance(StreamType.STOCK_DATA)

                self._init_stream()
                if self._stream is None:
                    logger.error("Failed to initialize stream - stream is None")
                    return

                self._is_running = True
                logger.info(
                    f"Data stream connecting to Alpaca WebSocket... "
                    f"Subscriptions: bars={len(self._subscribed_bars)}, "
                    f"quotes={len(self._subscribed_quotes)}"
                )

                # Notify reconnection if this is a retry (not first attempt)
                if not is_first_attempt:
                    for callback in self._on_reconnect_callbacks:
                        try:
                            callback()
                        except Exception as e:
                            logger.error(f"Error in reconnect callback: {e}")

                is_first_attempt = False
                await self._stream._run_forever()

                # If _run_forever returns normally, the connection succeeded
                # at some point. Reset retry counter.
                conn_mgr.record_connected(StreamType.STOCK_DATA)
                self._reconnect_attempts = 0

            except Exception as e:
                self._is_running = False
                error_msg = str(e)
                logger.error(f"Data stream disconnected: {error_msg}")

                # Immediately close the old stream to release the socket.
                await self._close_stream()
                conn_mgr.record_disconnected(StreamType.STOCK_DATA)

                # Notify disconnect callbacks
                for callback in self._on_disconnect_callbacks:
                    try:
                        callback(error_msg)
                    except Exception as cb_error:
                        logger.error(f"Error in disconnect callback: {cb_error}")

                if not self._should_reconnect:
                    raise

                # Detect "connection limit exceeded" or HTTP 429
                is_connection_limit = "connection limit" in error_msg.lower() or "429" in error_msg

                if is_connection_limit:
                    # Connection-limit errors are NOT counted toward the
                    # max-reconnect cap.  They are transient — the old
                    # connection just needs time to expire on Alpaca's side.
                    conn_mgr.record_connection_limit_error(StreamType.STOCK_DATA)
                    backoff = conn_mgr.get_connection_limit_backoff(StreamType.STOCK_DATA)
                    logger.warning(
                        f"Connection limit exceeded — waiting {backoff:.0f}s "
                        f"for old connection to expire on Alpaca's side "
                        f"(attempt counter stays at {self._reconnect_attempts}/"
                        f"{MAX_RECONNECT_ATTEMPTS})"
                    )
                    await asyncio.sleep(backoff)
                else:
                    # Non-connection-limit failure — count toward max retries.
                    self._reconnect_attempts += 1
                    if self._reconnect_attempts >= MAX_RECONNECT_ATTEMPTS:
                        logger.error(
                            f"Max reconnection attempts ({MAX_RECONNECT_ATTEMPTS}) "
                            f"reached for non-connection-limit errors"
                        )
                        raise

                    delay = min(
                        INITIAL_RECONNECT_DELAY * (2**self._reconnect_attempts),
                        MAX_RECONNECT_DELAY,
                    )
                    logger.warning(
                        f"Reconnecting in {delay:.1f}s "
                        f"(attempt {self._reconnect_attempts}/{MAX_RECONNECT_ATTEMPTS})"
                    )
                    await asyncio.sleep(delay)

    async def _close_stream(self) -> None:
        """Close the current stream and release the connection."""
        if self._stream is not None:
            try:
                await self._stream.stop()
            except Exception as close_err:
                logger.debug(f"Error closing stream (expected during reconnect): {close_err}")
            finally:
                self._stream = None

    def run_sync(self, auto_reconnect: bool = True) -> None:
        """
        Run the data stream synchronously (blocking) with reconnection.

        Uses the same connection-limit handling as ``start()``:
        - Connection-limit errors are not counted toward the retry cap.
        - Escalating backoff via ``ConnectionManager`` (120 s, 240 s, …).

        Args:
            auto_reconnect: Whether to automatically reconnect on disconnect
        """
        import time

        conn_mgr = get_connection_manager()
        self._should_reconnect = auto_reconnect
        self._reconnect_attempts = 0
        is_first_attempt = True

        while True:
            try:
                self._init_stream()
                if self._stream is None:
                    return

                self._is_running = True
                logger.info("Starting data stream (sync)...")

                if not is_first_attempt:
                    for callback in self._on_reconnect_callbacks:
                        try:
                            callback()
                        except Exception as e:
                            logger.error(f"Error in reconnect callback: {e}")

                is_first_attempt = False
                self._stream.run()

                conn_mgr.record_connected(StreamType.STOCK_DATA)
                self._reconnect_attempts = 0

            except Exception as e:
                self._is_running = False
                error_msg = str(e)
                logger.error(f"Data stream disconnected: {error_msg}")

                # Close old stream immediately
                if self._stream is not None:
                    with contextlib.suppress(Exception):
                        self._stream.stop()
                    self._stream = None
                conn_mgr.record_disconnected(StreamType.STOCK_DATA)

                for callback in self._on_disconnect_callbacks:
                    try:
                        callback(error_msg)
                    except Exception as cb_error:
                        logger.error(f"Error in disconnect callback: {cb_error}")

                if not self._should_reconnect:
                    raise

                is_connection_limit = "connection limit" in error_msg.lower() or "429" in error_msg

                if is_connection_limit:
                    conn_mgr.record_connection_limit_error(StreamType.STOCK_DATA)
                    backoff = conn_mgr.get_connection_limit_backoff(StreamType.STOCK_DATA)
                    logger.warning(
                        f"Connection limit exceeded — waiting {backoff:.0f}s "
                        f"(attempt counter stays at {self._reconnect_attempts}/"
                        f"{MAX_RECONNECT_ATTEMPTS})"
                    )
                    time.sleep(backoff)
                else:
                    self._reconnect_attempts += 1
                    if self._reconnect_attempts >= MAX_RECONNECT_ATTEMPTS:
                        logger.error(
                            f"Max reconnection attempts ({MAX_RECONNECT_ATTEMPTS}) "
                            f"reached for non-connection-limit errors"
                        )
                        raise

                    delay = min(
                        INITIAL_RECONNECT_DELAY * (2**self._reconnect_attempts),
                        MAX_RECONNECT_DELAY,
                    )
                    logger.warning(
                        f"Reconnecting in {delay:.1f}s "
                        f"(attempt {self._reconnect_attempts}/{MAX_RECONNECT_ATTEMPTS})"
                    )
                    time.sleep(delay)

    async def stop(self) -> None:
        """Stop the data stream and prevent reconnection."""
        self._should_reconnect = False
        self._is_running = False
        await self._close_stream()
        get_connection_manager().record_disconnected(StreamType.STOCK_DATA)
        logger.info("Data stream stopped")

    def is_running(self) -> bool:
        """Check if the stream is running."""
        return self._is_running

    def get_subscriptions(self) -> dict[str, set[str]]:
        """Get current subscriptions."""
        return {
            "bars": self._subscribed_bars.copy(),
            "quotes": self._subscribed_quotes.copy(),
            "trades": self._subscribed_trades.copy(),
        }

    def get_health_status(self) -> dict[str, Any]:
        """
        Get connection health status for monitoring.

        Per Alpaca's terms, we must monitor for connectivity issues.
        This method provides health information for alerting.
        """

        now = datetime.now()
        last_data_age = None
        is_stale = False

        if self._last_data_time:
            last_data_age = (now - self._last_data_time).total_seconds()
            # Consider data stale if no updates in 60 seconds during market hours
            is_stale = last_data_age > 60

        return {
            "is_running": self._is_running,
            "is_connected": self._is_running and self._stream is not None,
            "reconnect_attempts": self._reconnect_attempts,
            "last_data_time": self._last_data_time.isoformat() if self._last_data_time else None,
            "last_data_age_seconds": last_data_age,
            "is_stale": is_stale,
            "feed": self._feed.value,
            "subscriptions": {
                "bars": len(self._subscribed_bars),
                "quotes": len(self._subscribed_quotes),
                "trades": len(self._subscribed_trades),
            },
        }
