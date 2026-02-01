"""End-of-Day Reversal Strategy.

Concept: Catch reversals in the final hour of trading.
Assets: SPY, QQQ (high liquidity for late-day trading)
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


class EODReversal(BaseStrategy):
    """
    End-of-Day Reversal Strategy.

    Entry Rules:
    - After 3:00 PM ET
    - Identify intraday trend
    - Enter counter-trend if:
      * RSI >75 (overbought) → short
      * RSI <25 (oversold) → long
      * VWAP deviation >2%

    Exit Rules:
    - Hold until 3:55 PM ET (close before market close)
    - Stop loss: 1% from entry
    - Take profit: 1.5% from entry
    """

    DEFAULT_PARAMS = {
        "start_hour": TradingConstants.EOD_START_HOUR,
        "rsi_oversold": TradingConstants.EOD_RSI_OVERSOLD,
        "rsi_overbought": TradingConstants.EOD_RSI_OVERBOUGHT,
        "vwap_deviation_pct": TradingConstants.EOD_VWAP_DEVIATION_PCT,
        "stop_loss_pct": TradingConstants.EOD_STOP_LOSS_PCT,
        "take_profit_pct": TradingConstants.EOD_TAKE_PROFIT_PCT,
        "exit_minute": TradingConstants.EOD_EXIT_MINUTE,
        "position_size_pct": TradingConstants.EOD_POSITION_SIZE_PCT,
        "max_positions": TradingConstants.EOD_MAX_POSITIONS,
        "allowed_symbols": list(TradingConstants.TIER_1_ASSETS),
        "min_volume": 10_000_000,
    }

    def __init__(
        self,
        strategy_id: UUID | None = None,
        parameters: dict[str, Any] | None = None,
    ):
        merged_params = {**self.DEFAULT_PARAMS, **(parameters or {})}

        super().__init__(
            strategy_id=strategy_id,
            name="EOD Reversal",
            version="1.0.0",
            strategy_type=StrategyType.EOD_REVERSAL,
            parameters=merged_params,
        )

        self._et_tz = pytz.timezone("America/New_York")

    def _get_market_time(self) -> datetime:
        """Get current time in Eastern timezone."""
        return datetime.now(self._et_tz)

    def _is_trading_period(self) -> bool:
        """Check if we're in the EOD trading window."""
        now = self._get_market_time()
        start_time = time(self.parameters["start_hour"], 0)
        exit_time = time(15, self.parameters["exit_minute"])  # 3:55 PM
        return start_time <= now.time() < exit_time

    def _should_force_exit(self) -> bool:
        """Check if we should force exit all positions before close."""
        now = self._get_market_time()
        exit_time = time(15, self.parameters["exit_minute"])
        return now.time() >= exit_time

    def _calculate_vwap_deviation(
        self, current_price: Decimal, vwap: Decimal
    ) -> float:
        """Calculate percentage deviation from VWAP."""
        return float((current_price - vwap) / vwap) * 100

    def _detect_intraday_trend(self, context: MarketContext) -> str:
        """
        Detect the intraday trend based on price vs VWAP and MA.
        Returns 'up', 'down', or 'sideways'.
        """
        if context.vwap is None:
            return "sideways"

        current_price = context.current_price
        vwap = context.vwap

        deviation = self._calculate_vwap_deviation(current_price, vwap)

        if deviation > 1.0:
            return "up"
        elif deviation < -1.0:
            return "down"
        else:
            return "sideways"

    def should_enter(self, context: MarketContext) -> StrategySignal | None:
        """Check if entry conditions are met for EOD reversal."""
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

        # Need RSI and VWAP for this strategy
        if context.rsi is None or context.vwap is None:
            return None

        current_price = context.current_price
        rsi = context.rsi
        vwap = context.vwap
        deviation = self._calculate_vwap_deviation(current_price, vwap)
        trend = self._detect_intraday_trend(context)

        indicators = {
            "rsi": round(rsi, 2),
            "vwap": str(vwap),
            "vwap_deviation_pct": round(deviation, 2),
            "intraday_trend": trend,
            "current_price": str(current_price),
            "volume": context.volume,
            "time": self._get_market_time().strftime("%H:%M:%S"),
        }

        signal = None
        min_deviation = self.parameters["vwap_deviation_pct"]

        # Overbought reversal - short opportunity
        if (
            rsi > self.parameters["rsi_overbought"]
            and deviation > min_deviation
            and trend == "up"
        ):
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
                    f"EOD REVERSAL SHORT: {symbol} overbought at RSI {rsi:.1f}. "
                    f"Price {deviation:.2f}% above VWAP after uptrend. "
                    f"Expecting mean reversion before close. "
                    f"Target: ${take_profit}, Stop: ${stop_loss}"
                ),
                indicators=indicators,
            )
            logger.info(
                f"EOD Reversal SELL signal for {symbol} - "
                f"RSI: {rsi:.1f}, VWAP dev: {deviation:.2f}%"
            )

        # Oversold reversal - long opportunity
        elif (
            rsi < self.parameters["rsi_oversold"]
            and deviation < -min_deviation
            and trend == "down"
        ):
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
                    f"EOD REVERSAL LONG: {symbol} oversold at RSI {rsi:.1f}. "
                    f"Price {deviation:.2f}% below VWAP after downtrend. "
                    f"Expecting mean reversion before close. "
                    f"Target: ${take_profit}, Stop: ${stop_loss}"
                ),
                indicators=indicators,
            )
            logger.info(
                f"EOD Reversal BUY signal for {symbol} - "
                f"RSI: {rsi:.1f}, VWAP dev: {deviation:.2f}%"
            )

        return signal

    def should_exit(
        self, context: MarketContext, entry_price: Decimal, side: OrderSide
    ) -> tuple[bool, str]:
        """Check if exit conditions are met."""
        current_price = context.current_price

        # Force exit before market close
        if self._should_force_exit():
            return True, f"Forced exit at 3:{self.parameters['exit_minute']} PM ET before market close"

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

    def calculate_position_size(
        self, context: MarketContext, account_value: Decimal
    ) -> Decimal:
        """Calculate position size based on account value."""
        position_pct = Decimal(self.parameters["position_size_pct"]) / 100
        return account_value * position_pct

    def reset_daily(self) -> None:
        """Reset state for a new trading day."""
        self._open_positions.clear()
        logger.info(f"{self.name}: Daily state reset")
