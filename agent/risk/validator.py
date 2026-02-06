"""Pre-trade validation to ensure all risk rules are met."""

from dataclasses import dataclass
from datetime import datetime, time
from decimal import Decimal

import pytz
from loguru import logger

from agent.config.constants import OrderSide, TradingConstants
from agent.config.settings import get_settings
from agent.strategies.base import StrategySignal


@dataclass
class ValidationResult:
    """Result of trade validation."""

    is_valid: bool
    reason: str
    warnings: list[str]
    failure_code: str | None = None  # e.g., "market_hours", "buying_power", "max_positions"


class TradeValidator:
    """
    Validates trades before execution to ensure all risk rules are met.

    Checks:
    - Trading hours
    - Position size limits
    - Maximum concurrent positions
    - Stop loss is set
    - Symbol is tradeable
    - Account has sufficient buying power
    """

    def __init__(self):
        self._settings = get_settings()
        self._et_tz = pytz.timezone("America/New_York")

    def _get_market_time(self) -> datetime:
        """Get current time in Eastern timezone."""
        return datetime.now(self._et_tz)

    def _is_market_hours(self) -> tuple[bool, str]:
        """Check if within market hours (with buffer)."""
        now = self._get_market_time()
        current_time = now.time()

        # Calculate open time with buffer (add minutes, handle overflow)
        open_minutes = self._settings.market_open_minute + self._settings.avoid_first_minutes
        open_hour = self._settings.market_open_hour + (open_minutes // 60)
        open_minutes = open_minutes % 60
        market_open = time(open_hour, open_minutes)

        # Calculate close time with buffer (subtract minutes, handle underflow)
        close_minutes = self._settings.market_close_minute - self._settings.avoid_last_minutes
        close_hour = self._settings.market_close_hour
        if close_minutes < 0:
            close_hour -= 1
            close_minutes += 60
        market_close = time(close_hour, close_minutes)

        if current_time < market_open:
            return False, f"Before market open (opens at {market_open})"
        if current_time > market_close:
            return False, f"After market close (closed at {market_close})"

        return True, "Within trading hours"

    def validate_signal(
        self,
        signal: StrategySignal,
        account_value: Decimal,
        buying_power: Decimal,
        current_positions: int,
        current_positions_value: Decimal,
        daytrading_buying_power: Decimal | None = None,
        is_pattern_day_trader: bool = False,
    ) -> ValidationResult:
        """
        Validate a trading signal before execution.

        Args:
            signal: The strategy signal to validate
            account_value: Current account equity
            buying_power: Available buying power (max of regt_buying_power, daytrading_buying_power)
            current_positions: Number of current open positions
            current_positions_value: Total value of current positions
            daytrading_buying_power: Day trading specific buying power (4x margin for PDT accounts)
            is_pattern_day_trader: Whether account is flagged as Pattern Day Trader

        Returns:
            ValidationResult with validation status
        """
        warnings: list[str] = []

        # Check market hours
        in_hours, hours_reason = self._is_market_hours()
        if not in_hours:
            return ValidationResult(
                is_valid=False,
                reason=hours_reason,
                warnings=warnings,
                failure_code="market_hours",
            )

        # Validate stop loss is set
        if signal.stop_loss is None or signal.stop_loss <= 0:
            return ValidationResult(
                is_valid=False,
                reason="Stop loss not set - all trades MUST have a stop loss",
                warnings=warnings,
                failure_code="no_stop_loss",
            )

        # Validate stop loss is reasonable
        if signal.side == OrderSide.BUY:
            if signal.stop_loss >= signal.entry_price:
                return ValidationResult(
                    is_valid=False,
                    reason=f"Invalid stop loss ${signal.stop_loss} >= entry ${signal.entry_price} for BUY",
                    warnings=warnings,
                    failure_code="invalid_stop_loss",
                )
            stop_distance_pct = (
                float((signal.entry_price - signal.stop_loss) / signal.entry_price) * 100
            )
        else:
            if signal.stop_loss <= signal.entry_price:
                return ValidationResult(
                    is_valid=False,
                    reason=f"Invalid stop loss ${signal.stop_loss} <= entry ${signal.entry_price} for SELL",
                    warnings=warnings,
                    failure_code="invalid_stop_loss",
                )
            stop_distance_pct = (
                float((signal.stop_loss - signal.entry_price) / signal.entry_price) * 100
            )

        # Warn if stop loss is very tight or very wide
        if stop_distance_pct < 0.3:
            warnings.append(
                f"Stop loss very tight ({stop_distance_pct:.2f}%) - may trigger on noise"
            )
        if stop_distance_pct > 5.0:
            warnings.append(
                f"Stop loss very wide ({stop_distance_pct:.2f}%) - large potential loss"
            )

        # Validate position size
        position_value = account_value * Decimal(signal.position_size_pct / 100)
        max_position_value = account_value * Decimal(self._settings.max_position_size_pct / 100)

        if position_value > max_position_value:
            return ValidationResult(
                is_valid=False,
                reason=f"Position ${position_value:.2f} exceeds max ${max_position_value:.2f}",
                warnings=warnings,
                failure_code="position_size",
            )

        # Check buying power
        # For PDT accounts, validate against daytrading_buying_power to prevent DTMC
        if is_pattern_day_trader and daytrading_buying_power is not None:
            if position_value > daytrading_buying_power:
                logger.warning(
                    f"DTMC Prevention: Position ${position_value:.2f} exceeds "
                    f"daytrading_buying_power ${daytrading_buying_power:.2f} "
                    f"(regt buying_power: ${buying_power:.2f})"
                )
                return ValidationResult(
                    is_valid=False,
                    reason=f"Insufficient day trading buying power (need ${position_value:.2f}, "
                    f"have ${daytrading_buying_power:.2f} DT BP, ${buying_power:.2f} RegT BP)",
                    warnings=warnings,
                    failure_code="daytrading_buying_power",
                )
        elif position_value > buying_power:
            return ValidationResult(
                is_valid=False,
                reason=f"Insufficient buying power (need ${position_value:.2f}, have ${buying_power:.2f})",
                warnings=warnings,
                failure_code="buying_power",
            )

        # Check max concurrent positions
        if current_positions >= self._settings.max_concurrent_positions:
            return ValidationResult(
                is_valid=False,
                reason=f"Max concurrent positions ({self._settings.max_concurrent_positions}) reached",
                warnings=warnings,
                failure_code="max_positions",
            )

        # Check total exposure
        new_total_exposure = current_positions_value + position_value
        max_exposure = account_value * Decimal(0.60)  # 60% max deployed
        if new_total_exposure > max_exposure:
            return ValidationResult(
                is_valid=False,
                reason=f"Would exceed max exposure (new total ${new_total_exposure:.2f} > max ${max_exposure:.2f})",
                warnings=warnings,
                failure_code="max_exposure",
            )

        # Check risk/reward ratio
        if signal.risk_reward_ratio < 1.0:
            warnings.append(
                f"Risk/reward ratio {signal.risk_reward_ratio:.2f} < 1.0 - consider better entry"
            )

        # Validate confidence
        if signal.confidence < 0.5:
            warnings.append(f"Low confidence signal ({signal.confidence:.2f})")

        # Check minimum price
        if signal.entry_price < TradingConstants.MIN_STOCK_PRICE:
            return ValidationResult(
                is_valid=False,
                reason=f"Price ${signal.entry_price} below minimum ${TradingConstants.MIN_STOCK_PRICE}",
                warnings=warnings,
                failure_code="min_price",
            )

        logger.debug(
            f"Signal validated for {signal.symbol}: "
            f"side={signal.side.value}, entry=${signal.entry_price}, "
            f"stop=${signal.stop_loss}, position_pct={signal.position_size_pct}%"
        )

        return ValidationResult(
            is_valid=True,
            reason="All validation checks passed",
            warnings=warnings,
        )

    def validate_exit(
        self,
        symbol: str,
        current_price: Decimal,
        entry_price: Decimal,
        side: OrderSide,
    ) -> ValidationResult:
        """
        Validate an exit trade.

        Args:
            symbol: Stock symbol
            current_price: Current market price
            entry_price: Original entry price
            side: Original trade side
        """
        warnings: list[str] = []

        # Calculate P&L
        if side == OrderSide.BUY:
            pnl_pct = float((current_price - entry_price) / entry_price) * 100
        else:
            pnl_pct = float((entry_price - current_price) / entry_price) * 100

        if pnl_pct < -2.0:
            warnings.append(f"Large loss on exit: {pnl_pct:.2f}%")

        # Check market hours for exit
        in_hours, hours_reason = self._is_market_hours()
        if not in_hours:
            # Allow exits outside hours in emergencies
            warnings.append(f"Exiting outside normal hours: {hours_reason}")

        return ValidationResult(
            is_valid=True,
            reason="Exit validated",
            warnings=warnings,
        )

    def can_trade_symbol(self, symbol: str) -> tuple[bool, str]:
        """
        Check if a symbol is allowed for trading.

        Args:
            symbol: Stock symbol to check
        """
        # Check against blacklist (could be loaded from config/db)
        blacklist = {"TQQQ", "SQQQ", "UVXY", "SVXY"}  # Leveraged ETFs
        if symbol.upper() in blacklist:
            return False, f"{symbol} is on the blacklist (leveraged/inverse ETF)"

        return True, "Symbol allowed"
