"""Momentum Scalping Strategy.

Concept: Ride strong intraday trends with quick scalps.
Assets: High-volume stocks with >5M daily volume
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytz
from loguru import logger

from agent.config.constants import OrderSide, StrategyType, TradingConstants
from agent.strategies.base import BaseStrategy, MarketContext, StrategySignal


class MomentumScalp(BaseStrategy):
    """
    Momentum Scalping Strategy.

    Entry Rules:
    - 5-min MACD crosses above signal (buy) or below (sell)
    - RSI between 40-60 (not extreme)
    - Volume >150% of 20-period average
    - Price above/below 50-period MA (trend confirmation)

    Exit Rules:
    - Take profit: 1.5% from entry
    - Stop loss: 0.6% from entry
    - Exit if MACD crosses back
    """

    DEFAULT_PARAMS = {
        "volume_ratio_threshold": TradingConstants.MOMENTUM_VOLUME_RATIO,
        "rsi_min": TradingConstants.MOMENTUM_RSI_MIN,
        "rsi_max": TradingConstants.MOMENTUM_RSI_MAX,
        "take_profit_pct": TradingConstants.MOMENTUM_TAKE_PROFIT_PCT,
        "stop_loss_pct": TradingConstants.MOMENTUM_STOP_LOSS_PCT,
        "position_size_pct": TradingConstants.MOMENTUM_POSITION_SIZE_PCT,
        "max_positions": TradingConstants.MOMENTUM_MAX_POSITIONS,
        "min_volume": 5_000_000,
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
            name="Momentum Scalp",
            version="1.0.0",
            strategy_type=StrategyType.MOMENTUM_SCALP,
            parameters=merged_params,
        )

        self._et_tz = pytz.timezone("America/New_York")
        # Track last MACD state for crossover detection
        self._last_macd_state: dict[str, str] = {}  # symbol -> 'above' or 'below'

    def _get_market_time(self) -> datetime:
        """Get current time in Eastern timezone."""
        return datetime.now(self._et_tz)

    def _detect_macd_crossover(
        self, symbol: str, macd: float, macd_signal: float
    ) -> str | None:
        """
        Detect MACD crossover.
        Returns 'bullish', 'bearish', or None.
        """
        current_state = "above" if macd > macd_signal else "below"
        last_state = self._last_macd_state.get(symbol)

        self._last_macd_state[symbol] = current_state

        if last_state is None:
            return None

        if last_state == "below" and current_state == "above":
            return "bullish"
        elif last_state == "above" and current_state == "below":
            return "bearish"

        return None

    def should_enter(self, context: MarketContext) -> StrategySignal | None:
        """Check if entry conditions are met for momentum scalping."""
        symbol = context.symbol

        # Validate basic entry conditions
        is_valid, reason = self.validate_entry(context)
        if not is_valid:
            return None

        # Check if we already have a position
        if self.has_position(symbol):
            return None

        # Check max positions
        if self.get_open_positions_count() >= self.parameters["max_positions"]:
            return None

        # Need MACD, RSI, and MA for this strategy
        if (
            context.macd is None
            or context.macd_signal is None
            or context.rsi is None
            or context.ma_50 is None
        ):
            return None

        current_price = context.current_price
        macd = context.macd
        macd_signal = context.macd_signal
        rsi = context.rsi
        ma_50 = context.ma_50

        # Check RSI is not extreme
        if not (self.parameters["rsi_min"] <= rsi <= self.parameters["rsi_max"]):
            return None

        # Detect MACD crossover
        crossover = self._detect_macd_crossover(symbol, macd, macd_signal)
        if crossover is None:
            return None

        indicators = {
            "macd": round(macd, 4),
            "macd_signal": round(macd_signal, 4),
            "rsi": round(rsi, 2),
            "ma_50": str(ma_50),
            "current_price": str(current_price),
            "volume": context.volume,
            "crossover": crossover,
        }

        signal = None

        # Bullish crossover + price above MA
        if crossover == "bullish" and current_price > ma_50:
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
                confidence=0.6,
                reasoning=(
                    f"MOMENTUM LONG: {symbol} bullish MACD crossover. "
                    f"MACD: {macd:.4f} > Signal: {macd_signal:.4f}. "
                    f"RSI neutral at {rsi:.1f}. Price above MA50 (${ma_50}). "
                    f"Target: ${take_profit}, Stop: ${stop_loss}"
                ),
                indicators=indicators,
            )
            logger.info(f"Momentum BUY signal for {symbol} - bullish MACD crossover")

        # Bearish crossover + price below MA
        elif crossover == "bearish" and current_price < ma_50:
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
                confidence=0.6,
                reasoning=(
                    f"MOMENTUM SHORT: {symbol} bearish MACD crossover. "
                    f"MACD: {macd:.4f} < Signal: {macd_signal:.4f}. "
                    f"RSI neutral at {rsi:.1f}. Price below MA50 (${ma_50}). "
                    f"Target: ${take_profit}, Stop: ${stop_loss}"
                ),
                indicators=indicators,
            )
            logger.info(f"Momentum SELL signal for {symbol} - bearish MACD crossover")

        return signal

    def should_exit(
        self, context: MarketContext, entry_price: Decimal, side: OrderSide
    ) -> tuple[bool, str]:
        """Check if exit conditions are met."""
        current_price = context.current_price

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

        # Check for MACD cross back (reversal)
        if context.macd is not None and context.macd_signal is not None:
            if side == OrderSide.BUY and context.macd < context.macd_signal:
                return True, "MACD crossed back below signal - momentum lost"
            if side == OrderSide.SELL and context.macd > context.macd_signal:
                return True, "MACD crossed back above signal - momentum lost"

        return False, ""

    def calculate_position_size(
        self, context: MarketContext, account_value: Decimal
    ) -> Decimal:
        """Calculate position size based on account value."""
        position_pct = Decimal(self.parameters["position_size_pct"]) / 100
        return account_value * position_pct

    def reset_daily(self) -> None:
        """Reset state for a new trading day."""
        self._open_positions.clear()
        self._last_macd_state.clear()
        logger.info(f"{self.name}: Daily state reset")
