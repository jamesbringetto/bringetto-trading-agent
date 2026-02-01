"""Alpaca broker integration for order execution."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide as AlpacaOrderSide
from alpaca.trading.enums import OrderStatus as AlpacaOrderStatus
from alpaca.trading.enums import TimeInForce
from alpaca.trading.requests import (
    GetOrdersRequest,
    LimitOrderRequest,
    MarketOrderRequest,
)
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.live import StockDataStream
from alpaca.data.requests import StockLatestQuoteRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from loguru import logger

from agent.config.settings import get_settings
from agent.config.constants import OrderSide, OrderStatus


@dataclass
class OrderResult:
    """Result of an order submission."""

    success: bool
    order_id: str | None
    filled_price: Decimal | None
    filled_qty: Decimal | None
    status: OrderStatus
    message: str
    raw_response: dict[str, Any] | None = None


@dataclass
class Position:
    """Current position information."""

    symbol: str
    qty: Decimal
    avg_entry_price: Decimal
    market_value: Decimal
    unrealized_pl: Decimal
    unrealized_plpc: Decimal
    side: str


@dataclass
class AccountInfo:
    """Account information."""

    equity: Decimal
    cash: Decimal
    buying_power: Decimal
    portfolio_value: Decimal
    day_trade_count: int
    pattern_day_trader: bool


class AlpacaBroker:
    """
    Alpaca broker client for trading operations.

    Handles:
    - Order submission (market, limit)
    - Position management
    - Account information
    - Real-time data streaming
    """

    def __init__(self):
        settings = get_settings()
        self._api_key = settings.alpaca_api_key
        self._secret_key = settings.alpaca_secret_key
        self._base_url = settings.alpaca_base_url
        self._is_paper = settings.is_paper_trading

        # Initialize trading client
        self._trading_client = TradingClient(
            api_key=self._api_key,
            secret_key=self._secret_key,
            paper=self._is_paper,
        )

        # Initialize data client
        self._data_client = StockHistoricalDataClient(
            api_key=self._api_key,
            secret_key=self._secret_key,
        )

        # Data stream will be initialized when needed
        self._data_stream: StockDataStream | None = None

        logger.info(
            f"AlpacaBroker initialized - Paper trading: {self._is_paper}"
        )

    def _convert_order_side(self, side: OrderSide) -> AlpacaOrderSide:
        """Convert internal order side to Alpaca enum."""
        return AlpacaOrderSide.BUY if side == OrderSide.BUY else AlpacaOrderSide.SELL

    def _convert_order_status(self, status: AlpacaOrderStatus) -> OrderStatus:
        """Convert Alpaca order status to internal enum."""
        status_map = {
            AlpacaOrderStatus.NEW: OrderStatus.SUBMITTED,
            AlpacaOrderStatus.ACCEPTED: OrderStatus.SUBMITTED,
            AlpacaOrderStatus.PENDING_NEW: OrderStatus.PENDING,
            AlpacaOrderStatus.FILLED: OrderStatus.FILLED,
            AlpacaOrderStatus.PARTIALLY_FILLED: OrderStatus.PARTIALLY_FILLED,
            AlpacaOrderStatus.CANCELED: OrderStatus.CANCELLED,
            AlpacaOrderStatus.REJECTED: OrderStatus.REJECTED,
            AlpacaOrderStatus.EXPIRED: OrderStatus.EXPIRED,
        }
        return status_map.get(status, OrderStatus.PENDING)

    async def submit_market_order(
        self,
        symbol: str,
        side: OrderSide,
        qty: Decimal | None = None,
        notional: Decimal | None = None,
    ) -> OrderResult:
        """
        Submit a market order.

        Args:
            symbol: Stock symbol
            side: Buy or sell
            qty: Number of shares (use either qty or notional)
            notional: Dollar amount to trade
        """
        try:
            order_data = MarketOrderRequest(
                symbol=symbol,
                side=self._convert_order_side(side),
                qty=float(qty) if qty else None,
                notional=float(notional) if notional else None,
                time_in_force=TimeInForce.DAY,
            )

            order = self._trading_client.submit_order(order_data)

            logger.info(
                f"Market order submitted: {side.value} {qty or notional} {symbol} "
                f"- Order ID: {order.id}"
            )

            return OrderResult(
                success=True,
                order_id=str(order.id),
                filled_price=Decimal(str(order.filled_avg_price)) if order.filled_avg_price else None,
                filled_qty=Decimal(str(order.filled_qty)) if order.filled_qty else None,
                status=self._convert_order_status(order.status),
                message=f"Order submitted successfully",
                raw_response=order.__dict__,
            )

        except Exception as e:
            logger.error(f"Failed to submit market order for {symbol}: {e}")
            return OrderResult(
                success=False,
                order_id=None,
                filled_price=None,
                filled_qty=None,
                status=OrderStatus.REJECTED,
                message=str(e),
            )

    async def submit_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        limit_price: Decimal,
        qty: Decimal,
    ) -> OrderResult:
        """
        Submit a limit order.

        Args:
            symbol: Stock symbol
            side: Buy or sell
            limit_price: Limit price
            qty: Number of shares
        """
        try:
            order_data = LimitOrderRequest(
                symbol=symbol,
                side=self._convert_order_side(side),
                limit_price=float(limit_price),
                qty=float(qty),
                time_in_force=TimeInForce.DAY,
            )

            order = self._trading_client.submit_order(order_data)

            logger.info(
                f"Limit order submitted: {side.value} {qty} {symbol} @ ${limit_price} "
                f"- Order ID: {order.id}"
            )

            return OrderResult(
                success=True,
                order_id=str(order.id),
                filled_price=Decimal(str(order.filled_avg_price)) if order.filled_avg_price else None,
                filled_qty=Decimal(str(order.filled_qty)) if order.filled_qty else None,
                status=self._convert_order_status(order.status),
                message=f"Order submitted successfully",
                raw_response=order.__dict__,
            )

        except Exception as e:
            logger.error(f"Failed to submit limit order for {symbol}: {e}")
            return OrderResult(
                success=False,
                order_id=None,
                filled_price=None,
                filled_qty=None,
                status=OrderStatus.REJECTED,
                message=str(e),
            )

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        try:
            self._trading_client.cancel_order_by_id(order_id)
            logger.info(f"Order cancelled: {order_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    async def cancel_all_orders(self) -> bool:
        """Cancel all open orders."""
        try:
            self._trading_client.cancel_orders()
            logger.info("All orders cancelled")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel all orders: {e}")
            return False

    def get_order(self, order_id: str) -> OrderResult | None:
        """Get order status by ID."""
        try:
            order = self._trading_client.get_order_by_id(order_id)
            return OrderResult(
                success=True,
                order_id=str(order.id),
                filled_price=Decimal(str(order.filled_avg_price)) if order.filled_avg_price else None,
                filled_qty=Decimal(str(order.filled_qty)) if order.filled_qty else None,
                status=self._convert_order_status(order.status),
                message="Order retrieved",
                raw_response=order.__dict__,
            )
        except Exception as e:
            logger.error(f"Failed to get order {order_id}: {e}")
            return None

    def get_open_orders(self) -> list[dict[str, Any]]:
        """Get all open orders."""
        try:
            request = GetOrdersRequest(status="open")
            orders = self._trading_client.get_orders(filter=request)
            return [
                {
                    "id": str(o.id),
                    "symbol": o.symbol,
                    "side": o.side.value,
                    "qty": float(o.qty) if o.qty else None,
                    "filled_qty": float(o.filled_qty) if o.filled_qty else None,
                    "status": o.status.value,
                    "created_at": o.created_at.isoformat() if o.created_at else None,
                }
                for o in orders
            ]
        except Exception as e:
            logger.error(f"Failed to get open orders: {e}")
            return []

    def get_positions(self) -> list[Position]:
        """Get all current positions."""
        try:
            positions = self._trading_client.get_all_positions()
            return [
                Position(
                    symbol=p.symbol,
                    qty=Decimal(str(p.qty)),
                    avg_entry_price=Decimal(str(p.avg_entry_price)),
                    market_value=Decimal(str(p.market_value)),
                    unrealized_pl=Decimal(str(p.unrealized_pl)),
                    unrealized_plpc=Decimal(str(p.unrealized_plpc)),
                    side=p.side.value,
                )
                for p in positions
            ]
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return []

    def get_position(self, symbol: str) -> Position | None:
        """Get position for a specific symbol."""
        try:
            p = self._trading_client.get_open_position(symbol)
            return Position(
                symbol=p.symbol,
                qty=Decimal(str(p.qty)),
                avg_entry_price=Decimal(str(p.avg_entry_price)),
                market_value=Decimal(str(p.market_value)),
                unrealized_pl=Decimal(str(p.unrealized_pl)),
                unrealized_plpc=Decimal(str(p.unrealized_plpc)),
                side=p.side.value,
            )
        except Exception:
            return None

    async def close_position(self, symbol: str) -> OrderResult:
        """Close an entire position."""
        try:
            order = self._trading_client.close_position(symbol)
            logger.info(f"Position closed: {symbol}")
            return OrderResult(
                success=True,
                order_id=str(order.id),
                filled_price=Decimal(str(order.filled_avg_price)) if order.filled_avg_price else None,
                filled_qty=Decimal(str(order.filled_qty)) if order.filled_qty else None,
                status=self._convert_order_status(order.status),
                message=f"Position closed",
            )
        except Exception as e:
            logger.error(f"Failed to close position {symbol}: {e}")
            return OrderResult(
                success=False,
                order_id=None,
                filled_price=None,
                filled_qty=None,
                status=OrderStatus.REJECTED,
                message=str(e),
            )

    async def close_all_positions(self) -> bool:
        """Close all positions (emergency exit)."""
        try:
            self._trading_client.close_all_positions(cancel_orders=True)
            logger.warning("ALL POSITIONS CLOSED - Emergency exit")
            return True
        except Exception as e:
            logger.error(f"Failed to close all positions: {e}")
            return False

    def get_account(self) -> AccountInfo | None:
        """Get account information."""
        try:
            account = self._trading_client.get_account()
            return AccountInfo(
                equity=Decimal(str(account.equity)),
                cash=Decimal(str(account.cash)),
                buying_power=Decimal(str(account.buying_power)),
                portfolio_value=Decimal(str(account.portfolio_value)),
                day_trade_count=account.daytrade_count,
                pattern_day_trader=account.pattern_day_trader,
            )
        except Exception as e:
            logger.error(f"Failed to get account info: {e}")
            return None

    def get_latest_quote(self, symbol: str) -> dict[str, Any] | None:
        """Get latest quote for a symbol."""
        try:
            request = StockLatestQuoteRequest(symbol_or_symbols=symbol)
            quotes = self._data_client.get_stock_latest_quote(request)
            quote = quotes[symbol]
            return {
                "symbol": symbol,
                "bid": float(quote.bid_price),
                "ask": float(quote.ask_price),
                "bid_size": quote.bid_size,
                "ask_size": quote.ask_size,
                "timestamp": quote.timestamp.isoformat(),
            }
        except Exception as e:
            logger.error(f"Failed to get quote for {symbol}: {e}")
            return None

    def get_bars(
        self,
        symbol: str,
        timeframe: TimeFrame,
        start: datetime,
        end: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Get historical bars for a symbol."""
        try:
            request = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=timeframe,
                start=start,
                end=end,
            )
            bars = self._data_client.get_stock_bars(request)
            return [
                {
                    "timestamp": bar.timestamp.isoformat(),
                    "open": float(bar.open),
                    "high": float(bar.high),
                    "low": float(bar.low),
                    "close": float(bar.close),
                    "volume": bar.volume,
                    "vwap": float(bar.vwap) if bar.vwap else None,
                }
                for bar in bars[symbol]
            ]
        except Exception as e:
            logger.error(f"Failed to get bars for {symbol}: {e}")
            return []

    def is_market_open(self) -> bool:
        """Check if the market is currently open."""
        try:
            clock = self._trading_client.get_clock()
            return clock.is_open
        except Exception as e:
            logger.error(f"Failed to check market status: {e}")
            return False

    def get_market_hours(self) -> dict[str, Any] | None:
        """Get market hours for today."""
        try:
            clock = self._trading_client.get_clock()
            return {
                "is_open": clock.is_open,
                "next_open": clock.next_open.isoformat() if clock.next_open else None,
                "next_close": clock.next_close.isoformat() if clock.next_close else None,
            }
        except Exception as e:
            logger.error(f"Failed to get market hours: {e}")
            return None

    def init_data_stream(self) -> StockDataStream:
        """Initialize and return the data stream for real-time data."""
        if self._data_stream is None:
            self._data_stream = StockDataStream(
                api_key=self._api_key,
                secret_key=self._secret_key,
            )
        return self._data_stream
