"""Alpaca broker integration for order execution.

This module provides a compliant integration with Alpaca's Trading and Data APIs.
It handles PDT protection, rate limiting, and proper error handling per Alpaca's
terms of service.

Compliance Notes:
- PDT protection is handled by checking day trade count before orders
- All order rejections are logged for compliance reporting
- Rate limiting with exponential backoff is implemented
- WebSocket reconnection is handled automatically
"""

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable

from alpaca.common.exceptions import APIError
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide as AlpacaOrderSide
from alpaca.trading.enums import OrderStatus as AlpacaOrderStatus
from alpaca.trading.enums import TimeInForce, QueryOrderStatus
from alpaca.trading.requests import (
    GetOrdersRequest,
    LimitOrderRequest,
    MarketOrderRequest,
    StopLimitOrderRequest,
    StopOrderRequest,
    TrailingStopOrderRequest,
    TakeProfitRequest,
    StopLossRequest,
)
from alpaca.trading.stream import TradingStream
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.live import StockDataStream
from alpaca.data.enums import DataFeed
from alpaca.data.requests import StockLatestQuoteRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from loguru import logger

from agent.config.settings import get_settings
from agent.config.constants import OrderSide, OrderStatus


# Constants for rate limiting
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 1.0

# PDT Protection threshold
PDT_EQUITY_THRESHOLD = Decimal("25000.00")
PDT_MAX_DAY_TRADES = 3  # Max day trades in 5 days before PDT flag


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
    daytrading_buying_power: Decimal | None = None


@dataclass
class PDTStatus:
    """Pattern Day Trader status information."""

    is_pdt: bool
    day_trade_count: int
    equity: Decimal
    can_day_trade: bool
    reason: str


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

    def _retry_with_backoff(self, func, *args, **kwargs):
        """
        Execute a function with exponential backoff retry on rate limit errors.

        Per Alpaca's terms, we must handle rate limiting gracefully.
        """
        last_exception = None
        for attempt in range(MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except APIError as e:
                last_exception = e
                # Check for rate limit (429) or server errors (5xx)
                if hasattr(e, 'status_code') and e.status_code in (429, 500, 502, 503, 504):
                    wait_time = INITIAL_BACKOFF_SECONDS * (2 ** attempt)
                    logger.warning(f"Rate limited or server error, retrying in {wait_time}s (attempt {attempt + 1}/{MAX_RETRIES})")
                    time.sleep(wait_time)
                else:
                    raise
            except Exception as e:
                raise
        raise last_exception

    def check_pdt_status(self) -> PDTStatus:
        """
        Check Pattern Day Trader status and whether day trading is allowed.

        Per FINRA rules:
        - PDT flag is set when 4+ day trades in 5 business days with margin account
        - Accounts with < $25,000 equity cannot day trade if flagged as PDT
        - Alpaca has built-in PDT protection that rejects orders with 403

        Returns:
            PDTStatus with current PDT information
        """
        try:
            account = self._trading_client.get_account()
            equity = Decimal(str(account.equity))
            day_trade_count = account.daytrade_count or 0
            is_pdt = account.pattern_day_trader or False

            # Determine if day trading is allowed
            if is_pdt and equity < PDT_EQUITY_THRESHOLD:
                can_day_trade = False
                reason = f"PDT flagged with equity ${equity:.2f} < ${PDT_EQUITY_THRESHOLD}"
            elif day_trade_count >= PDT_MAX_DAY_TRADES and equity < PDT_EQUITY_THRESHOLD:
                can_day_trade = False
                reason = f"At {day_trade_count} day trades, next trade would trigger PDT with equity < ${PDT_EQUITY_THRESHOLD}"
            else:
                can_day_trade = True
                reason = "Day trading allowed"

            logger.debug(f"PDT Status: is_pdt={is_pdt}, count={day_trade_count}, equity=${equity:.2f}, can_trade={can_day_trade}")

            return PDTStatus(
                is_pdt=is_pdt,
                day_trade_count=day_trade_count,
                equity=equity,
                can_day_trade=can_day_trade,
                reason=reason,
            )
        except Exception as e:
            logger.error(f"Failed to check PDT status: {e}")
            # Default to conservative - don't allow if we can't check
            return PDTStatus(
                is_pdt=False,
                day_trade_count=0,
                equity=Decimal(0),
                can_day_trade=False,
                reason=f"Unable to verify PDT status: {e}",
            )

    def _handle_api_error(self, e: Exception, symbol: str, action: str) -> OrderResult:
        """
        Handle Alpaca API errors with proper logging for compliance.

        Per Alpaca's terms, all order errors must be logged.
        """
        error_msg = str(e)

        # Check for PDT rejection (403)
        if isinstance(e, APIError) and hasattr(e, 'status_code'):
            if e.status_code == 403:
                logger.error(
                    f"PDT PROTECTION: Order rejected for {symbol} - {action}. "
                    f"Account may be at risk of PDT flag. Error: {error_msg}"
                )
                return OrderResult(
                    success=False,
                    order_id=None,
                    filled_price=None,
                    filled_qty=None,
                    status=OrderStatus.REJECTED,
                    message=f"PDT Protection: {error_msg}",
                )
            elif e.status_code == 422:
                logger.error(f"Invalid order for {symbol}: {error_msg}")
            elif e.status_code == 429:
                logger.error(f"Rate limited when submitting order for {symbol}")

        logger.error(f"Order failed for {symbol} ({action}): {error_msg}")
        return OrderResult(
            success=False,
            order_id=None,
            filled_price=None,
            filled_qty=None,
            status=OrderStatus.REJECTED,
            message=error_msg,
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

    def submit_market_order(
        self,
        symbol: str,
        side: OrderSide,
        qty: Decimal | None = None,
        notional: Decimal | None = None,
        check_pdt: bool = True,
    ) -> OrderResult:
        """
        Submit a market order.

        Args:
            symbol: Stock symbol
            side: Buy or sell
            qty: Number of shares (use either qty or notional)
            notional: Dollar amount to trade
            check_pdt: Whether to check PDT status before submitting (default True)

        Note: This is a synchronous method as Alpaca's SDK is synchronous.
        """
        # Check PDT status for exit orders (which would complete a day trade)
        if check_pdt and side == OrderSide.SELL:
            pdt_status = self.check_pdt_status()
            if not pdt_status.can_day_trade:
                logger.warning(f"PDT check failed for {symbol}: {pdt_status.reason}")
                # Log but don't block - Alpaca will reject if truly problematic
                # This is informational to help the strategy adjust

        try:
            order_data = MarketOrderRequest(
                symbol=symbol,
                side=self._convert_order_side(side),
                qty=float(qty) if qty else None,
                notional=float(notional) if notional else None,
                time_in_force=TimeInForce.DAY,
            )

            # Use retry with backoff for rate limiting
            order = self._retry_with_backoff(
                self._trading_client.submit_order,
                order_data
            )

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
                message="Order submitted successfully",
                raw_response=order.__dict__,
            )

        except Exception as e:
            return self._handle_api_error(e, symbol, f"market {side.value}")

    def submit_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        limit_price: Decimal,
        qty: Decimal,
        time_in_force: TimeInForce = TimeInForce.DAY,
    ) -> OrderResult:
        """
        Submit a limit order.

        Args:
            symbol: Stock symbol
            side: Buy or sell
            limit_price: Limit price
            qty: Number of shares
            time_in_force: Order duration (default: DAY)

        Note: This is a synchronous method as Alpaca's SDK is synchronous.
        """
        try:
            order_data = LimitOrderRequest(
                symbol=symbol,
                side=self._convert_order_side(side),
                limit_price=float(limit_price),
                qty=float(qty),
                time_in_force=time_in_force,
            )

            order = self._retry_with_backoff(
                self._trading_client.submit_order,
                order_data
            )

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
                message="Order submitted successfully",
                raw_response=order.__dict__,
            )

        except Exception as e:
            return self._handle_api_error(e, symbol, f"limit {side.value}")

    def submit_stop_order(
        self,
        symbol: str,
        side: OrderSide,
        stop_price: Decimal,
        qty: Decimal,
    ) -> OrderResult:
        """
        Submit a stop order.

        Args:
            symbol: Stock symbol
            side: Buy or sell
            stop_price: Stop trigger price
            qty: Number of shares
        """
        try:
            order_data = StopOrderRequest(
                symbol=symbol,
                side=self._convert_order_side(side),
                stop_price=float(stop_price),
                qty=float(qty),
                time_in_force=TimeInForce.DAY,
            )

            order = self._retry_with_backoff(
                self._trading_client.submit_order,
                order_data
            )

            logger.info(
                f"Stop order submitted: {side.value} {qty} {symbol} @ stop ${stop_price} "
                f"- Order ID: {order.id}"
            )

            return OrderResult(
                success=True,
                order_id=str(order.id),
                filled_price=None,
                filled_qty=None,
                status=self._convert_order_status(order.status),
                message="Stop order submitted successfully",
                raw_response=order.__dict__,
            )

        except Exception as e:
            return self._handle_api_error(e, symbol, f"stop {side.value}")

    def submit_stop_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        stop_price: Decimal,
        limit_price: Decimal,
        qty: Decimal,
    ) -> OrderResult:
        """
        Submit a stop-limit order (used for stop losses).

        Args:
            symbol: Stock symbol
            side: Buy or sell
            stop_price: Stop trigger price
            limit_price: Limit price after stop triggers
            qty: Number of shares
        """
        try:
            order_data = StopLimitOrderRequest(
                symbol=symbol,
                side=self._convert_order_side(side),
                stop_price=float(stop_price),
                limit_price=float(limit_price),
                qty=float(qty),
                time_in_force=TimeInForce.DAY,
            )

            order = self._retry_with_backoff(
                self._trading_client.submit_order,
                order_data
            )

            logger.info(
                f"Stop-limit order submitted: {side.value} {qty} {symbol} "
                f"@ stop ${stop_price} / limit ${limit_price} - Order ID: {order.id}"
            )

            return OrderResult(
                success=True,
                order_id=str(order.id),
                filled_price=None,
                filled_qty=None,
                status=self._convert_order_status(order.status),
                message="Stop-limit order submitted successfully",
                raw_response=order.__dict__,
            )

        except Exception as e:
            return self._handle_api_error(e, symbol, f"stop-limit {side.value}")

    def submit_trailing_stop_order(
        self,
        symbol: str,
        side: OrderSide,
        qty: Decimal,
        trail_price: Decimal | None = None,
        trail_percent: Decimal | None = None,
    ) -> OrderResult:
        """
        Submit a trailing stop order.

        Per Alpaca SDK: Must specify exactly one of trail_price or trail_percent.

        Args:
            symbol: Stock symbol
            side: Buy or sell
            qty: Number of shares
            trail_price: Dollar amount to trail (e.g., $1.00 trail)
            trail_percent: Percentage to trail (e.g., 1.0 for 1%)

        Raises:
            ValueError: If neither or both trail_price and trail_percent are specified
        """
        # Validate - must have exactly one of trail_price or trail_percent
        if (trail_price is None) == (trail_percent is None):
            raise ValueError("Must specify exactly one of trail_price or trail_percent")

        try:
            order_data = TrailingStopOrderRequest(
                symbol=symbol,
                side=self._convert_order_side(side),
                qty=float(qty),
                trail_price=float(trail_price) if trail_price else None,
                trail_percent=float(trail_percent) if trail_percent else None,
                time_in_force=TimeInForce.DAY,
            )

            order = self._retry_with_backoff(
                self._trading_client.submit_order,
                order_data
            )

            trail_info = f"${trail_price}" if trail_price else f"{trail_percent}%"
            logger.info(
                f"Trailing stop order submitted: {side.value} {qty} {symbol} "
                f"trail {trail_info} - Order ID: {order.id}"
            )

            return OrderResult(
                success=True,
                order_id=str(order.id),
                filled_price=None,
                filled_qty=None,
                status=self._convert_order_status(order.status),
                message="Trailing stop order submitted successfully",
                raw_response=order.__dict__,
            )

        except Exception as e:
            return self._handle_api_error(e, symbol, f"trailing-stop {side.value}")

    def submit_bracket_order(
        self,
        symbol: str,
        side: OrderSide,
        qty: Decimal,
        take_profit_price: Decimal,
        stop_loss_price: Decimal,
        stop_loss_limit_price: Decimal | None = None,
        entry_type: str = "market",
        limit_price: Decimal | None = None,
    ) -> OrderResult:
        """
        Submit a bracket order with take profit and stop loss attached.

        This creates an OCO (One-Cancels-Other) bracket where:
        - Entry order fills first
        - Take profit (limit) and stop loss orders are placed
        - When one child order fills, the other is cancelled

        Args:
            symbol: Stock symbol
            side: Buy or sell for entry
            qty: Number of shares
            take_profit_price: Limit price for take profit
            stop_loss_price: Stop price for stop loss
            stop_loss_limit_price: Limit price for stop loss (optional, creates stop-limit)
            entry_type: "market" or "limit" for entry order
            limit_price: Required if entry_type is "limit"
        """
        try:
            # Build take profit leg
            take_profit = TakeProfitRequest(limit_price=float(take_profit_price))

            # Build stop loss leg (can be stop or stop-limit)
            if stop_loss_limit_price:
                stop_loss = StopLossRequest(
                    stop_price=float(stop_loss_price),
                    limit_price=float(stop_loss_limit_price),
                )
            else:
                stop_loss = StopLossRequest(stop_price=float(stop_loss_price))

            # Build the appropriate entry order
            if entry_type == "limit":
                if limit_price is None:
                    raise ValueError("limit_price required for limit entry orders")
                order_data = LimitOrderRequest(
                    symbol=symbol,
                    side=self._convert_order_side(side),
                    qty=float(qty),
                    limit_price=float(limit_price),
                    time_in_force=TimeInForce.DAY,
                    order_class="bracket",
                    take_profit=take_profit,
                    stop_loss=stop_loss,
                )
            else:
                order_data = MarketOrderRequest(
                    symbol=symbol,
                    side=self._convert_order_side(side),
                    qty=float(qty),
                    time_in_force=TimeInForce.DAY,
                    order_class="bracket",
                    take_profit=take_profit,
                    stop_loss=stop_loss,
                )

            order = self._retry_with_backoff(
                self._trading_client.submit_order,
                order_data
            )

            logger.info(
                f"Bracket order submitted: {side.value} {qty} {symbol} "
                f"TP=${take_profit_price} SL=${stop_loss_price} - Order ID: {order.id}"
            )

            return OrderResult(
                success=True,
                order_id=str(order.id),
                filled_price=Decimal(str(order.filled_avg_price)) if order.filled_avg_price else None,
                filled_qty=Decimal(str(order.filled_qty)) if order.filled_qty else None,
                status=self._convert_order_status(order.status),
                message="Bracket order submitted successfully",
                raw_response=order.__dict__,
            )

        except Exception as e:
            return self._handle_api_error(e, symbol, f"bracket {side.value}")

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order."""
        try:
            self._retry_with_backoff(
                self._trading_client.cancel_order_by_id,
                order_id
            )
            logger.info(f"Order cancelled: {order_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id}: {e}")
            return False

    def cancel_all_orders(self) -> bool:
        """Cancel all open orders."""
        try:
            self._retry_with_backoff(self._trading_client.cancel_orders)
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
            request = GetOrdersRequest(status=QueryOrderStatus.OPEN)
            orders = self._retry_with_backoff(
                self._trading_client.get_orders,
                filter=request
            )
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

    def close_position(self, symbol: str) -> OrderResult:
        """Close an entire position."""
        try:
            order = self._retry_with_backoff(
                self._trading_client.close_position,
                symbol
            )
            logger.info(f"Position closed: {symbol}")
            return OrderResult(
                success=True,
                order_id=str(order.id),
                filled_price=Decimal(str(order.filled_avg_price)) if order.filled_avg_price else None,
                filled_qty=Decimal(str(order.filled_qty)) if order.filled_qty else None,
                status=self._convert_order_status(order.status),
                message="Position closed",
            )
        except Exception as e:
            return self._handle_api_error(e, symbol, "close position")

    def close_all_positions(self) -> bool:
        """
        Close all positions (emergency exit).

        This is used by the kill switch and circuit breaker.
        """
        try:
            self._retry_with_backoff(
                self._trading_client.close_all_positions,
                cancel_orders=True
            )
            logger.warning("ALL POSITIONS CLOSED - Emergency exit")
            return True
        except Exception as e:
            logger.error(f"Failed to close all positions: {e}")
            return False

    def get_account(self) -> AccountInfo | None:
        """Get account information including PDT status."""
        try:
            account = self._retry_with_backoff(self._trading_client.get_account)
            return AccountInfo(
                equity=Decimal(str(account.equity)),
                cash=Decimal(str(account.cash)),
                buying_power=Decimal(str(account.buying_power)),
                portfolio_value=Decimal(str(account.portfolio_value)),
                day_trade_count=account.daytrade_count or 0,
                pattern_day_trader=account.pattern_day_trader or False,
                daytrading_buying_power=Decimal(str(account.daytrading_buying_power)) if account.daytrading_buying_power else None,
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

    def init_data_stream(self, feed: DataFeed = DataFeed.IEX) -> StockDataStream:
        """
        Initialize and return the data stream for real-time data.

        Args:
            feed: Data feed to use (IEX is free, SIP requires subscription)
                - DataFeed.IEX: Free, 15-min delayed for non-subscribers
                - DataFeed.SIP: Real-time, requires Alpaca market data subscription

        Returns:
            StockDataStream instance for subscribing to real-time data
        """
        if self._data_stream is None:
            self._data_stream = StockDataStream(
                api_key=self._api_key,
                secret_key=self._secret_key,
                feed=feed,
            )
            logger.info(f"Data stream initialized with {feed.value} feed")
        return self._data_stream


class OrderUpdateHandler:
    """
    Real-time order update handler using Alpaca's TradingStream.

    Provides callbacks for order fills, cancellations, and other events
    to enable real-time position and P&L tracking.
    """

    def __init__(self):
        settings = get_settings()
        self._api_key = settings.alpaca_api_key
        self._secret_key = settings.alpaca_secret_key
        self._is_paper = settings.is_paper_trading

        self._trading_stream: TradingStream | None = None
        self._is_running = False

        # Callbacks for different event types
        self._on_fill_callbacks: list[Callable[[dict], None]] = []
        self._on_partial_fill_callbacks: list[Callable[[dict], None]] = []
        self._on_cancel_callbacks: list[Callable[[dict], None]] = []
        self._on_reject_callbacks: list[Callable[[dict], None]] = []

        logger.info("OrderUpdateHandler initialized")

    def on_fill(self, callback: Callable[[dict], None]) -> None:
        """Register callback for order fills."""
        self._on_fill_callbacks.append(callback)

    def on_partial_fill(self, callback: Callable[[dict], None]) -> None:
        """Register callback for partial fills."""
        self._on_partial_fill_callbacks.append(callback)

    def on_cancel(self, callback: Callable[[dict], None]) -> None:
        """Register callback for order cancellations."""
        self._on_cancel_callbacks.append(callback)

    def on_reject(self, callback: Callable[[dict], None]) -> None:
        """Register callback for order rejections."""
        self._on_reject_callbacks.append(callback)

    async def _handle_trade_update(self, data) -> None:
        """
        Handle incoming trade updates from the TradingStream.

        Trade update events include:
        - new: Order received
        - fill: Order completely filled
        - partial_fill: Order partially filled
        - canceled: Order canceled
        - expired: Order expired
        - rejected: Order rejected
        - replaced: Order replaced
        """
        try:
            event = data.event
            order = data.order

            update_info = {
                "event": event,
                "order_id": str(order.id),
                "symbol": order.symbol,
                "side": order.side.value,
                "qty": float(order.qty) if order.qty else None,
                "filled_qty": float(order.filled_qty) if order.filled_qty else None,
                "filled_avg_price": float(order.filled_avg_price) if order.filled_avg_price else None,
                "status": order.status.value,
                "timestamp": data.timestamp.isoformat() if hasattr(data, 'timestamp') else None,
            }

            logger.info(f"Trade update: {event} - {order.symbol} - Order {order.id}")

            # Route to appropriate callbacks
            if event == "fill":
                for callback in self._on_fill_callbacks:
                    try:
                        callback(update_info)
                    except Exception as e:
                        logger.error(f"Error in fill callback: {e}")

            elif event == "partial_fill":
                for callback in self._on_partial_fill_callbacks:
                    try:
                        callback(update_info)
                    except Exception as e:
                        logger.error(f"Error in partial fill callback: {e}")

            elif event in ("canceled", "expired"):
                for callback in self._on_cancel_callbacks:
                    try:
                        callback(update_info)
                    except Exception as e:
                        logger.error(f"Error in cancel callback: {e}")

            elif event == "rejected":
                logger.error(f"Order rejected: {order.symbol} - {order.id}")
                for callback in self._on_reject_callbacks:
                    try:
                        callback(update_info)
                    except Exception as e:
                        logger.error(f"Error in reject callback: {e}")

        except Exception as e:
            logger.error(f"Error handling trade update: {e}")

    def _init_stream(self) -> None:
        """Initialize the trading stream."""
        if self._trading_stream is None:
            self._trading_stream = TradingStream(
                api_key=self._api_key,
                secret_key=self._secret_key,
                paper=self._is_paper,
            )
            self._trading_stream.subscribe_trade_updates(self._handle_trade_update)

    async def start(self) -> None:
        """Start the trading stream for real-time order updates."""
        if self._is_running:
            logger.warning("OrderUpdateHandler already running")
            return

        self._init_stream()
        if self._trading_stream is None:
            return

        self._is_running = True
        logger.info("Starting trading stream for order updates...")

        try:
            await self._trading_stream._run_forever()
        except Exception as e:
            self._is_running = False
            logger.error(f"Trading stream error: {e}")
            raise

    def run_sync(self) -> None:
        """Run the trading stream synchronously (blocking)."""
        self._init_stream()
        if self._trading_stream is None:
            return

        self._is_running = True
        logger.info("Starting trading stream (sync)...")

        try:
            self._trading_stream.run()
        except Exception as e:
            self._is_running = False
            logger.error(f"Trading stream error: {e}")
            raise

    async def stop(self) -> None:
        """Stop the trading stream."""
        if self._trading_stream and self._is_running:
            await self._trading_stream.stop()
            self._is_running = False
            logger.info("Trading stream stopped")

    def is_running(self) -> bool:
        """Check if the stream is running."""
        return self._is_running
