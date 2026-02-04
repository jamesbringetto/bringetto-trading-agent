"""VWAP Mean Reversion Strategy.

Concept: Fade extreme deviations from VWAP.
Assets: Large-cap tech (AAPL, MSFT, GOOGL, NVDA, TSLA)
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytz
from loguru import logger

from agent.config.constants import OrderSide, StrategyType, TradingConstants
from agent.strategies.base import BaseStrategy, MarketContext, StrategySignal


@dataclass
class VWAPPosition:
    """Track VWAP position entry details."""

    symbol: str
    entry_time: datetime
    entry_price: Decimal
    entry_vwap: Decimal


class VWAPReversion(BaseStrategy):
    """
    VWAP Mean Reversion Strategy.

    Entry Rules:
    - Price deviates >1.5% from VWAP
    - RSI confirms oversold (<30) or overbought (>70)
    - Enter in direction of VWAP (buy if below, sell if above)

    Exit Rules:
    - Target: VWAP +/- 0.2%
    - Stop loss: 0.8% from entry
    - Max holding time: 60 minutes
    """

    DEFAULT_PARAMS = {
        "deviation_threshold_pct": TradingConstants.VWAP_DEVIATION_THRESHOLD_PCT,
        "rsi_oversold": TradingConstants.VWAP_RSI_OVERSOLD,
        "rsi_overbought": TradingConstants.VWAP_RSI_OVERBOUGHT,
        "target_pct": TradingConstants.VWAP_TARGET_PCT,
        "stop_loss_pct": TradingConstants.VWAP_STOP_LOSS_PCT,
        "take_profit_pct": TradingConstants.VWAP_TARGET_PCT,  # Target VWAP
        "max_hold_minutes": TradingConstants.VWAP_MAX_HOLD_MINUTES,
        "position_size_pct": TradingConstants.VWAP_POSITION_SIZE_PCT,
        "max_positions": TradingConstants.VWAP_MAX_POSITIONS,
        "allowed_symbols": list(TradingConstants.SP500_ASSETS),
        "min_volume": 1_000,  # Per-bar volume (lowered for paper trading)
    }

    def __init__(
        self,
        strategy_id: UUID | None = None,
        parameters: dict[str, Any] | None = None,
    ):
        merged_params = {**self.DEFAULT_PARAMS, **(parameters or {})}

        super().__init__(
            strategy_id=strategy_id,
            name="VWAP Mean Reversion",
            version="1.0.0",
            strategy_type=StrategyType.VWAP_REVERSION,
            parameters=merged_params,
        )

        self._position_details: dict[str, VWAPPosition] = {}
        self._et_tz = pytz.timezone("America/New_York")

    def _get_market_time(self) -> datetime:
        """Get current time in Eastern timezone."""
        return datetime.now(self._et_tz)

    def _calculate_vwap_deviation(
        self, current_price: Decimal, vwap: Decimal
    ) -> float:
        """Calculate percentage deviation from VWAP."""
        return float((current_price - vwap) / vwap) * 100

    def should_enter(self, context: MarketContext) -> StrategySignal | None:
        """Check if entry conditions are met for VWAP reversion."""
        symbol = context.symbol

        # Validate basic entry conditions
        is_valid, reason = self.validate_entry(context)
        if not is_valid:
            return None

        # Check if symbol is allowed
        if symbol not in self.parameters["allowed_symbols"]:
            return None

        # Check if we already have a position
        if self.has_position(symbol):
            return None

        # Check max positions
        if self.get_open_positions_count() >= self.parameters["max_positions"]:
            return None

        # Need VWAP and RSI for this strategy
        if context.vwap is None or context.rsi is None:
            return None

        current_price = context.current_price
        vwap = context.vwap
        rsi = context.rsi

        deviation = self._calculate_vwap_deviation(current_price, vwap)
        deviation_threshold = self.parameters["deviation_threshold_pct"]

        indicators = {
            "vwap": str(vwap),
            "deviation_pct": round(deviation, 2),
            "rsi": round(rsi, 2),
            "current_price": str(current_price),
            "volume": context.volume,
        }

        signal = None

        # Check for oversold (price below VWAP, RSI low)
        if deviation < -deviation_threshold and rsi < self.parameters["rsi_oversold"]:
            entry_price = current_price
            stop_loss = self.calculate_stop_loss(entry_price, OrderSide.BUY)
            # Target is VWAP with small buffer
            take_profit = vwap * Decimal(1 - self.parameters["target_pct"] / 100)

            signal = StrategySignal(
                symbol=symbol,
                side=OrderSide.BUY,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                position_size_pct=self.parameters["position_size_pct"],
                confidence=0.65 + (abs(deviation) / 100),  # Higher confidence for larger deviations
                reasoning=(
                    f"VWAP LONG: {symbol} is {deviation:.2f}% below VWAP (${vwap}). "
                    f"RSI oversold at {rsi:.1f}. "
                    f"Expecting reversion to VWAP. Target: ${take_profit}, Stop: ${stop_loss}"
                ),
                indicators=indicators,
            )
            logger.info(f"VWAP BUY signal for {symbol} - deviation: {deviation:.2f}%, RSI: {rsi:.1f}")

        # Check for overbought (price above VWAP, RSI high)
        elif deviation > deviation_threshold and rsi > self.parameters["rsi_overbought"]:
            entry_price = current_price
            stop_loss = self.calculate_stop_loss(entry_price, OrderSide.SELL)
            # Target is VWAP with small buffer
            take_profit = vwap * Decimal(1 + self.parameters["target_pct"] / 100)

            signal = StrategySignal(
                symbol=symbol,
                side=OrderSide.SELL,
                entry_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                position_size_pct=self.parameters["position_size_pct"],
                confidence=0.65 + (abs(deviation) / 100),
                reasoning=(
                    f"VWAP SHORT: {symbol} is {deviation:.2f}% above VWAP (${vwap}). "
                    f"RSI overbought at {rsi:.1f}. "
                    f"Expecting reversion to VWAP. Target: ${take_profit}, Stop: ${stop_loss}"
                ),
                indicators=indicators,
            )
            logger.info(f"VWAP SELL signal for {symbol} - deviation: {deviation:.2f}%, RSI: {rsi:.1f}")

        if signal:
            # Store position details for max hold time check
            self._position_details[symbol] = VWAPPosition(
                symbol=symbol,
                entry_time=self._get_market_time(),
                entry_price=current_price,
                entry_vwap=vwap,
            )

        return signal

    def should_exit(
        self, context: MarketContext, entry_price: Decimal, side: OrderSide
    ) -> tuple[bool, str]:
        """Check if exit conditions are met."""
        symbol = context.symbol
        current_price = context.current_price

        # Check max holding time
        position = self._position_details.get(symbol)
        if position:
            hold_time = self._get_market_time() - position.entry_time
            max_hold = timedelta(minutes=self.parameters["max_hold_minutes"])
            if hold_time >= max_hold:
                return True, f"Max holding time ({self.parameters['max_hold_minutes']} min) exceeded"

        # Check stop loss
        stop_loss = self.calculate_stop_loss(entry_price, side)
        if side == OrderSide.BUY and current_price <= stop_loss:
            return True, f"Stop loss hit at ${current_price}"
        if side == OrderSide.SELL and current_price >= stop_loss:
            return True, f"Stop loss hit at ${current_price}"

        # Check if price reverted to VWAP
        if context.vwap:
            deviation = abs(self._calculate_vwap_deviation(current_price, context.vwap))
            if deviation <= self.parameters["target_pct"]:
                return True, f"Price reverted to VWAP (deviation: {deviation:.2f}%)"

        return False, ""

    def calculate_position_size(
        self, context: MarketContext, account_value: Decimal
    ) -> Decimal:
        """Calculate position size based on account value."""
        position_pct = Decimal(self.parameters["position_size_pct"]) / 100
        return account_value * position_pct

    def remove_position(self, symbol: str) -> None:
        """Remove position and clean up details."""
        super().remove_position(symbol)
        self._position_details.pop(symbol, None)

    def reset_daily(self) -> None:
        """Reset state for a new trading day."""
        self._open_positions.clear()
        self._position_details.clear()
        logger.info(f"{self.name}: Daily state reset")
