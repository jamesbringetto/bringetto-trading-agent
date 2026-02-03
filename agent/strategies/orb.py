"""Opening Range Breakout (ORB) Strategy.

Concept: Trade breakouts from the first 15-30 minute range.
Assets: SPY, QQQ, IWM (high liquidity)
"""

from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytz
from loguru import logger

from agent.config.constants import OrderSide, StrategyType, TradingConstants
from agent.strategies.base import BaseStrategy, MarketContext, StrategySignal


@dataclass
class OpeningRange:
    """Stores the opening range for a symbol."""

    symbol: str
    high: Decimal
    low: Decimal
    established_at: datetime
    is_valid: bool = True


class OpeningRangeBreakout(BaseStrategy):
    """
    Opening Range Breakout Strategy.

    Entry Rules:
    - Wait for first 15 minutes (9:30-9:45 AM ET)
    - Establish high/low range
    - Buy on breakout above high + 0.1%
    - Sell on breakdown below low - 0.1%

    Exit Rules:
    - Stop loss: 1% from entry
    - Take profit: 2% from entry OR trailing stop
    - Exit all positions by 3:45 PM ET
    """

    # Default parameters
    DEFAULT_PARAMS = {
        "range_minutes": TradingConstants.ORB_RANGE_MINUTES,
        "breakout_threshold_pct": TradingConstants.ORB_BREAKOUT_THRESHOLD_PCT,
        "stop_loss_pct": TradingConstants.ORB_STOP_LOSS_PCT,
        "take_profit_pct": TradingConstants.ORB_TAKE_PROFIT_PCT,
        "position_size_pct": TradingConstants.ORB_POSITION_SIZE_PCT,
        "max_positions": TradingConstants.ORB_MAX_POSITIONS,
        "allowed_symbols": list(TradingConstants.TIER_1_ASSETS),
        "min_volume": 5_000_000,
        "exit_time_hour": 15,
        "exit_time_minute": 45,
    }

    def __init__(
        self,
        strategy_id: UUID | None = None,
        parameters: dict[str, Any] | None = None,
    ):
        # Merge default params with any overrides
        merged_params = {**self.DEFAULT_PARAMS, **(parameters or {})}

        super().__init__(
            strategy_id=strategy_id,
            name="Opening Range Breakout",
            version="1.0.0",
            strategy_type=StrategyType.ORB,
            parameters=merged_params,
        )

        # Track opening ranges for each symbol
        self._opening_ranges: dict[str, OpeningRange] = {}
        self._et_tz = pytz.timezone("America/New_York")

    def _get_market_time(self) -> datetime:
        """Get current time in Eastern timezone."""
        return datetime.now(self._et_tz)

    def _is_range_period(self) -> bool:
        """Check if we're still in the opening range period."""
        now = self._get_market_time()
        range_end = time(9, 30 + self.parameters["range_minutes"])
        return now.time() < range_end

    def _is_trading_period(self) -> bool:
        """Check if we're in the valid trading period (after range, before exit)."""
        now = self._get_market_time()
        range_end = time(9, 30 + self.parameters["range_minutes"])
        exit_time = time(
            self.parameters["exit_time_hour"], self.parameters["exit_time_minute"]
        )
        return range_end <= now.time() < exit_time

    def _should_force_exit(self) -> bool:
        """Check if we should force exit all positions."""
        now = self._get_market_time()
        exit_time = time(
            self.parameters["exit_time_hour"], self.parameters["exit_time_minute"]
        )
        return now.time() >= exit_time

    def update_opening_range(
        self, symbol: str, high: Decimal, low: Decimal, force: bool = False
    ) -> None:
        """Update the opening range for a symbol during the range period.

        Args:
            symbol: Stock symbol
            high: High price to update range with
            low: Low price to update range with
            force: If True, bypass time check (for testing)
        """
        if not force and not self._is_range_period():
            return

        if symbol in self._opening_ranges:
            existing = self._opening_ranges[symbol]
            self._opening_ranges[symbol] = OpeningRange(
                symbol=symbol,
                high=max(existing.high, high),
                low=min(existing.low, low),
                established_at=self._get_market_time(),
            )
        else:
            self._opening_ranges[symbol] = OpeningRange(
                symbol=symbol,
                high=high,
                low=low,
                established_at=self._get_market_time(),
            )

    def get_opening_range(self, symbol: str) -> OpeningRange | None:
        """Get the established opening range for a symbol."""
        return self._opening_ranges.get(symbol)

    def reset_daily(self) -> None:
        """Reset state for a new trading day."""
        self._opening_ranges.clear()
        self._open_positions.clear()
        logger.info(f"{self.name}: Daily state reset")

    def should_enter(self, context: MarketContext) -> StrategySignal | None:
        """Check if entry conditions are met for ORB strategy."""
        symbol = context.symbol

        # Validate basic entry conditions
        is_valid, reason = self.validate_entry(context)
        if not is_valid:
            return None

        # Check if symbol is allowed
        if symbol not in self.parameters["allowed_symbols"]:
            return None

        # Check if we're in trading period
        if not self._is_trading_period():
            return None

        # Check if we already have a position
        if self.has_position(symbol):
            return None

        # Check max positions
        if self.get_open_positions_count() >= self.parameters["max_positions"]:
            return None

        # Get opening range
        opening_range = self.get_opening_range(symbol)
        if not opening_range or not opening_range.is_valid:
            return None

        current_price = context.current_price
        breakout_threshold = Decimal(1 + self.parameters["breakout_threshold_pct"] / 100)
        breakdown_threshold = Decimal(1 - self.parameters["breakout_threshold_pct"] / 100)

        signal = None
        indicators = {
            "opening_range_high": str(opening_range.high),
            "opening_range_low": str(opening_range.low),
            "current_price": str(current_price),
            "volume": context.volume,
            "vwap": str(context.vwap) if context.vwap else None,
        }

        # Check for breakout above range high
        breakout_level = opening_range.high * breakout_threshold
        if current_price >= breakout_level:
            entry_price = current_price
            stop_loss = self.calculate_stop_loss(entry_price, OrderSide.BUY)
            take_profit = self.calculate_take_profit(entry_price, OrderSide.BUY)

            signal = StrategySignal(
                symbol=symbol,
                side=OrderSide.BUY,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                position_size_pct=self.parameters["position_size_pct"],
                confidence=0.7,
                reasoning=(
                    f"ORB LONG: {symbol} broke above opening range high "
                    f"(${opening_range.high}) with breakout at ${current_price}. "
                    f"Volume: {context.volume:,}. Target: ${take_profit}, Stop: ${stop_loss}"
                ),
                indicators=indicators,
            )
            logger.info(f"ORB BUY signal for {symbol} at ${current_price}")

        # Check for breakdown below range low
        breakdown_level = opening_range.low * breakdown_threshold
        if current_price <= breakdown_level:
            entry_price = current_price
            stop_loss = self.calculate_stop_loss(entry_price, OrderSide.SELL)
            take_profit = self.calculate_take_profit(entry_price, OrderSide.SELL)

            signal = StrategySignal(
                symbol=symbol,
                side=OrderSide.SELL,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                position_size_pct=self.parameters["position_size_pct"],
                confidence=0.7,
                reasoning=(
                    f"ORB SHORT: {symbol} broke below opening range low "
                    f"(${opening_range.low}) with breakdown at ${current_price}. "
                    f"Volume: {context.volume:,}. Target: ${take_profit}, Stop: ${stop_loss}"
                ),
                indicators=indicators,
            )
            logger.info(f"ORB SELL signal for {symbol} at ${current_price}")

        return signal

    def should_exit(
        self, context: MarketContext, entry_price: Decimal, side: OrderSide
    ) -> tuple[bool, str]:
        """Check if exit conditions are met."""
        current_price = context.current_price

        # Force exit if past exit time
        if self._should_force_exit():
            return True, f"Forced exit at {self.parameters['exit_time_hour']}:{self.parameters['exit_time_minute']} ET"

        # Check stop loss
        stop_loss = self.calculate_stop_loss(entry_price, side)
        if side == OrderSide.BUY and current_price <= stop_loss:
            return True, f"Stop loss hit at ${current_price} (stop: ${stop_loss})"
        if side == OrderSide.SELL and current_price >= stop_loss:
            return True, f"Stop loss hit at ${current_price} (stop: ${stop_loss})"

        # Check take profit
        take_profit = self.calculate_take_profit(entry_price, side)
        if side == OrderSide.BUY and current_price >= take_profit:
            return True, f"Take profit hit at ${current_price} (target: ${take_profit})"
        if side == OrderSide.SELL and current_price <= take_profit:
            return True, f"Take profit hit at ${current_price} (target: ${take_profit})"

        return False, ""

    def calculate_position_size(
        self, context: MarketContext, account_value: Decimal
    ) -> Decimal:
        """Calculate position size based on account value and risk parameters."""
        position_pct = Decimal(self.parameters["position_size_pct"]) / 100
        return account_value * position_pct
