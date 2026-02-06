"""Pre-Market Gap & Go Strategy.

Concept: Trade stocks that gap significantly overnight.
Assets: Stocks with pre-market gap >3%
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
class GapInfo:
    """Information about a stock's gap."""

    symbol: str
    previous_close: Decimal
    premarket_price: Decimal
    gap_percent: float
    gap_direction: str  # 'up' or 'down'
    premarket_volume: int
    detected_at: datetime


class GapAndGo(BaseStrategy):
    """
    Pre-Market Gap & Go Strategy.

    Entry Rules:
    - Identify gaps >3% in pre-market
    - Wait for market open + 5 minutes (9:35 AM)
    - Enter on first pullback (0.5-1%) in gap direction
    - Volume must be >200k in first 5 minutes

    Exit Rules:
    - Take profit: Gap fill or 5% gain (whichever first)
    - Stop loss: 2% from entry
    - Exit by 10:30 AM (avoid mid-day chop)
    """

    DEFAULT_PARAMS = {
        "min_gap_pct": TradingConstants.GAP_MIN_PCT,
        "entry_delay_minutes": TradingConstants.GAP_ENTRY_DELAY_MINUTES,
        "pullback_pct": TradingConstants.GAP_PULLBACK_PCT,
        "min_premarket_volume": TradingConstants.GAP_MIN_PREMARKET_VOLUME,
        "stop_loss_pct": TradingConstants.GAP_STOP_LOSS_PCT,
        "take_profit_pct": TradingConstants.GAP_MAX_PROFIT_PCT,
        "position_size_pct": TradingConstants.GAP_POSITION_SIZE_PCT,
        "max_positions": TradingConstants.GAP_MAX_POSITIONS,
        "allowed_symbols": list(TradingConstants.SP500_ASSETS),
        "exit_time_hour": TradingConstants.GAP_EXIT_TIME_HOUR,
        "exit_time_minute": TradingConstants.GAP_EXIT_TIME_MINUTE,
        "min_price": 10.0,
    }

    def __init__(
        self,
        strategy_id: UUID | None = None,
        parameters: dict[str, Any] | None = None,
    ):
        merged_params = {**self.DEFAULT_PARAMS, **(parameters or {})}

        super().__init__(
            strategy_id=strategy_id,
            name="Gap and Go",
            version="1.0.0",
            strategy_type=StrategyType.GAP_AND_GO,
            parameters=merged_params,
        )

        self._et_tz = pytz.timezone("America/New_York")
        self._gaps: dict[str, GapInfo] = {}
        self._entry_prices_today: dict[str, Decimal] = {}  # Track high/low after open

    def _get_market_time(self) -> datetime:
        """Get current time in Eastern timezone."""
        return datetime.now(self._et_tz)

    def _is_trading_period(self) -> bool:
        """Check if we're in the valid trading period for gap trading."""
        now = self._get_market_time()
        entry_start = time(9, 30 + self.parameters["entry_delay_minutes"])
        exit_time = time(self.parameters["exit_time_hour"], self.parameters["exit_time_minute"])
        return entry_start <= now.time() < exit_time

    def _should_force_exit(self) -> bool:
        """Check if we should force exit all positions."""
        now = self._get_market_time()
        exit_time = time(self.parameters["exit_time_hour"], self.parameters["exit_time_minute"])
        return now.time() >= exit_time

    def register_gap(
        self,
        symbol: str,
        previous_close: Decimal,
        premarket_price: Decimal,
        premarket_volume: int,
    ) -> GapInfo | None:
        """
        Register a gap discovered in pre-market.
        Call this during pre-market scanning.
        """
        gap_percent = float((premarket_price - previous_close) / previous_close) * 100

        # Check minimum gap
        if abs(gap_percent) < self.parameters["min_gap_pct"]:
            return None

        # Check minimum volume
        if premarket_volume < self.parameters["min_premarket_volume"]:
            return None

        gap_direction = "up" if gap_percent > 0 else "down"

        gap_info = GapInfo(
            symbol=symbol,
            previous_close=previous_close,
            premarket_price=premarket_price,
            gap_percent=gap_percent,
            gap_direction=gap_direction,
            premarket_volume=premarket_volume,
            detected_at=self._get_market_time(),
        )

        self._gaps[symbol] = gap_info
        logger.info(
            f"Gap registered: {symbol} {gap_direction} {gap_percent:.2f}% "
            f"(prev close: ${previous_close}, premarket: ${premarket_price})"
        )

        return gap_info

    def get_gap(self, symbol: str) -> GapInfo | None:
        """Get gap information for a symbol."""
        return self._gaps.get(symbol)

    def update_price_action(self, symbol: str, high: Decimal, low: Decimal) -> None:
        """Update high/low after market open to detect pullback."""
        if symbol not in self._entry_prices_today:
            self._entry_prices_today[symbol] = {"high": high, "low": low}
        else:
            self._entry_prices_today[symbol]["high"] = max(
                self._entry_prices_today[symbol]["high"], high
            )
            self._entry_prices_today[symbol]["low"] = min(
                self._entry_prices_today[symbol]["low"], low
            )

    def should_enter(self, context: MarketContext) -> StrategySignal | None:
        """Check if entry conditions are met for gap trading."""
        symbol = context.symbol

        # Validate basic entry conditions
        is_valid, reason = self.validate_entry(context)
        if not is_valid:
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

        # Get gap information
        gap = self.get_gap(symbol)
        if gap is None:
            return None

        current_price = context.current_price
        price_action = self._entry_prices_today.get(symbol)

        if price_action is None:
            return None

        indicators = {
            "gap_percent": round(gap.gap_percent, 2),
            "gap_direction": gap.gap_direction,
            "previous_close": str(gap.previous_close),
            "premarket_price": str(gap.premarket_price),
            "current_price": str(current_price),
            "day_high": str(price_action["high"]),
            "day_low": str(price_action["low"]),
            "volume": context.volume,
        }

        signal = None
        pullback_pct = self.parameters["pullback_pct"] / 100

        # Gap Up - look for pullback from high
        if gap.gap_direction == "up":
            day_high = price_action["high"]
            pullback_level = day_high * Decimal(1 - pullback_pct)

            # Check if price has pulled back enough
            if pullback_level <= current_price < day_high:
                entry_price = current_price
                stop_loss = self.calculate_stop_loss(entry_price, OrderSide.BUY)
                # Target is either gap fill or max profit
                gap_fill_target = gap.premarket_price
                max_profit_target = entry_price * Decimal(
                    1 + self.parameters["take_profit_pct"] / 100
                )
                take_profit = min(gap_fill_target, max_profit_target)

                signal = StrategySignal(
                    symbol=symbol,
                    side=OrderSide.BUY,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    position_size_pct=self.parameters["position_size_pct"],
                    confidence=0.65,
                    reasoning=(
                        f"GAP UP LONG: {symbol} gapped up {gap.gap_percent:.2f}%. "
                        f"Pulled back {pullback_pct * 100:.1f}% from high of ${day_high}. "
                        f"Entry: ${current_price}. Target: ${take_profit}, Stop: ${stop_loss}"
                    ),
                    indicators=indicators,
                )
                logger.info(
                    f"Gap & Go BUY signal for {symbol} - "
                    f"gap: {gap.gap_percent:.2f}%, pullback entry at ${current_price}"
                )

        # Gap Down - look for pullback from low
        elif gap.gap_direction == "down":
            day_low = price_action["low"]
            pullback_level = day_low * Decimal(1 + pullback_pct)

            # Check if price has pulled back enough
            if day_low < current_price <= pullback_level:
                entry_price = current_price
                stop_loss = self.calculate_stop_loss(entry_price, OrderSide.SELL)
                # Target is either gap fill or max profit
                gap_fill_target = gap.premarket_price
                max_profit_target = entry_price * Decimal(
                    1 - self.parameters["take_profit_pct"] / 100
                )
                take_profit = max(gap_fill_target, max_profit_target)

                signal = StrategySignal(
                    symbol=symbol,
                    side=OrderSide.SELL,
                    entry_price=entry_price,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
                    position_size_pct=self.parameters["position_size_pct"],
                    confidence=0.65,
                    reasoning=(
                        f"GAP DOWN SHORT: {symbol} gapped down {gap.gap_percent:.2f}%. "
                        f"Pulled back {pullback_pct * 100:.1f}% from low of ${day_low}. "
                        f"Entry: ${current_price}. Target: ${take_profit}, Stop: ${stop_loss}"
                    ),
                    indicators=indicators,
                )
                logger.info(
                    f"Gap & Go SELL signal for {symbol} - "
                    f"gap: {gap.gap_percent:.2f}%, pullback entry at ${current_price}"
                )

        return signal

    def should_exit(
        self, context: MarketContext, entry_price: Decimal, side: OrderSide
    ) -> tuple[bool, str]:
        """Check if exit conditions are met."""
        current_price = context.current_price

        # Force exit if past exit time
        if self._should_force_exit():
            return (
                True,
                f"Forced exit at {self.parameters['exit_time_hour']}:{self.parameters['exit_time_minute']} ET",
            )

        # Check stop loss
        stop_loss = self.calculate_stop_loss(entry_price, side)
        if side == OrderSide.BUY and current_price <= stop_loss:
            return True, f"Stop loss hit at ${current_price}"
        if side == OrderSide.SELL and current_price >= stop_loss:
            return True, f"Stop loss hit at ${current_price}"

        # Check take profit
        take_profit = self.calculate_take_profit(entry_price, side)
        if side == OrderSide.BUY and current_price >= take_profit:
            return True, f"Take profit hit at ${current_price}"
        if side == OrderSide.SELL and current_price <= take_profit:
            return True, f"Take profit hit at ${current_price}"

        return False, ""

    def calculate_position_size(self, context: MarketContext, account_value: Decimal) -> Decimal:
        """Calculate position size based on account value."""
        position_pct = Decimal(self.parameters["position_size_pct"]) / 100
        return account_value * position_pct

    def reset_daily(self) -> None:
        """Reset state for a new trading day."""
        self._open_positions.clear()
        self._gaps.clear()
        self._entry_prices_today.clear()
        logger.info(f"{self.name}: Daily state reset")
