"""Real-time market data streaming via WebSocket."""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable

from alpaca.data.live import StockDataStream
from alpaca.data.models import Bar, Quote, Trade
from loguru import logger

from agent.config.settings import get_settings


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
    """

    def __init__(self):
        settings = get_settings()
        self._api_key = settings.alpaca_api_key
        self._secret_key = settings.alpaca_secret_key

        self._stream: StockDataStream | None = None
        self._is_running = False

        # Callbacks
        self._bar_callbacks: list[Callable[[BarData], None]] = []
        self._quote_callbacks: list[Callable[[QuoteData], None]] = []
        self._trade_callbacks: list[Callable[[TradeData], None]] = []

        # Subscribed symbols
        self._subscribed_bars: set[str] = set()
        self._subscribed_quotes: set[str] = set()
        self._subscribed_trades: set[str] = set()

        logger.info("DataStreamer initialized")

    def _init_stream(self) -> None:
        """Initialize the data stream."""
        if self._stream is None:
            self._stream = StockDataStream(
                api_key=self._api_key,
                secret_key=self._secret_key,
            )

    async def _handle_bar(self, bar: Bar) -> None:
        """Handle incoming bar data."""
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
        """Subscribe to bar data for symbols."""
        self._init_stream()
        if self._stream is None:
            return

        new_symbols = set(symbols) - self._subscribed_bars
        if new_symbols:
            self._stream.subscribe_bars(self._handle_bar, *new_symbols)
            self._subscribed_bars.update(new_symbols)
            logger.info(f"Subscribed to bars: {new_symbols}")

    async def subscribe_quotes(self, symbols: list[str]) -> None:
        """Subscribe to quote data for symbols."""
        self._init_stream()
        if self._stream is None:
            return

        new_symbols = set(symbols) - self._subscribed_quotes
        if new_symbols:
            self._stream.subscribe_quotes(self._handle_quote, *new_symbols)
            self._subscribed_quotes.update(new_symbols)
            logger.info(f"Subscribed to quotes: {new_symbols}")

    async def subscribe_trades(self, symbols: list[str]) -> None:
        """Subscribe to trade data for symbols."""
        self._init_stream()
        if self._stream is None:
            return

        new_symbols = set(symbols) - self._subscribed_trades
        if new_symbols:
            self._stream.subscribe_trades(self._handle_trade, *new_symbols)
            self._subscribed_trades.update(new_symbols)
            logger.info(f"Subscribed to trades: {new_symbols}")

    async def start(self) -> None:
        """Start the data stream."""
        if self._is_running:
            logger.warning("DataStreamer already running")
            return

        self._init_stream()
        if self._stream is None:
            return

        self._is_running = True
        logger.info("Starting data stream...")

        try:
            await self._stream._run_forever()
        except Exception as e:
            logger.error(f"Data stream error: {e}")
            self._is_running = False
            raise

    def run_sync(self) -> None:
        """Run the data stream synchronously (blocking)."""
        self._init_stream()
        if self._stream is None:
            return

        self._is_running = True
        logger.info("Starting data stream (sync)...")

        try:
            self._stream.run()
        except Exception as e:
            logger.error(f"Data stream error: {e}")
            self._is_running = False
            raise

    async def stop(self) -> None:
        """Stop the data stream."""
        if self._stream and self._is_running:
            await self._stream.stop()
            self._is_running = False
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
