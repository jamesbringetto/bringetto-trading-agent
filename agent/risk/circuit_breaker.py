"""Circuit breaker for automatic trading halts based on loss limits."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Callable

import pytz
from loguru import logger

from agent.config.settings import get_settings


@dataclass
class CircuitBreakerState:
    """Current state of the circuit breaker."""

    is_triggered: bool = False
    trigger_reason: str | None = None
    triggered_at: datetime | None = None
    resume_at: datetime | None = None
    daily_pnl: Decimal = Decimal(0)
    weekly_pnl: Decimal = Decimal(0)
    monthly_pnl: Decimal = Decimal(0)
    trades_today: int = 0


class CircuitBreaker:
    """
    Circuit breaker that halts trading when loss limits are exceeded.

    Monitors:
    - Daily loss limit (2% default)
    - Weekly loss limit (5% default)
    - Monthly drawdown (10% default)
    - Max trades per day
    - Strategy consecutive losses
    """

    def __init__(self, on_trigger: Callable[[str], None] | None = None):
        """
        Initialize circuit breaker.

        Args:
            on_trigger: Callback function called when circuit breaker triggers
        """
        self._settings = get_settings()
        self._et_tz = pytz.timezone("America/New_York")
        self._on_trigger = on_trigger

        # State tracking
        self._state = CircuitBreakerState()
        self._last_reset_date: datetime | None = None
        self._week_start_date: datetime | None = None
        self._month_start_date: datetime | None = None

        # Strategy loss tracking
        self._strategy_consecutive_losses: dict[str, int] = {}

        logger.info(
            f"CircuitBreaker initialized - "
            f"Daily limit: {self._settings.max_daily_loss_pct}%, "
            f"Weekly limit: {self._settings.max_weekly_loss_pct}%, "
            f"Monthly limit: {self._settings.max_monthly_drawdown_pct}%"
        )

    def _get_now(self) -> datetime:
        """Get current time in Eastern timezone."""
        return datetime.now(self._et_tz)

    def _check_daily_reset(self) -> None:
        """Check if we need to reset daily counters."""
        now = self._get_now()
        today = now.date()

        if self._last_reset_date is None or self._last_reset_date != today:
            self._state.daily_pnl = Decimal(0)
            self._state.trades_today = 0
            self._last_reset_date = today

            # Reset daily circuit breaker if it was triggered
            if self._state.is_triggered and self._state.trigger_reason == "daily_loss":
                self._state.is_triggered = False
                self._state.trigger_reason = None
                self._state.triggered_at = None
                self._state.resume_at = None
                logger.info("Daily circuit breaker reset for new trading day")

    def _check_weekly_reset(self) -> None:
        """Check if we need to reset weekly counters."""
        now = self._get_now()
        week_start = now.date() - timedelta(days=now.weekday())

        if self._week_start_date is None or self._week_start_date != week_start:
            self._state.weekly_pnl = Decimal(0)
            self._week_start_date = week_start

            if self._state.is_triggered and self._state.trigger_reason == "weekly_loss":
                self._state.is_triggered = False
                self._state.trigger_reason = None
                self._state.triggered_at = None
                self._state.resume_at = None
                logger.info("Weekly circuit breaker reset for new week")

    def _check_monthly_reset(self) -> None:
        """Check if we need to reset monthly counters."""
        now = self._get_now()
        month_start = now.date().replace(day=1)

        if self._month_start_date is None or self._month_start_date != month_start:
            self._state.monthly_pnl = Decimal(0)
            self._month_start_date = month_start

    def _trigger(self, reason: str, resume_at: datetime | None = None) -> None:
        """Trigger the circuit breaker."""
        self._state.is_triggered = True
        self._state.trigger_reason = reason
        self._state.triggered_at = self._get_now()
        self._state.resume_at = resume_at

        logger.warning(
            f"CIRCUIT BREAKER TRIGGERED: {reason}. "
            f"Trading halted until {resume_at or 'manual reset'}"
        )

        if self._on_trigger:
            self._on_trigger(reason)

    def record_trade(self, pnl: Decimal, strategy_name: str) -> None:
        """
        Record a completed trade and check limits.

        Args:
            pnl: Profit/loss from the trade
            strategy_name: Name of the strategy that made the trade
        """
        self._check_daily_reset()
        self._check_weekly_reset()
        self._check_monthly_reset()

        # Update P&L tracking
        self._state.daily_pnl += pnl
        self._state.weekly_pnl += pnl
        self._state.monthly_pnl += pnl
        self._state.trades_today += 1

        # Track consecutive losses per strategy
        if pnl < 0:
            self._strategy_consecutive_losses[strategy_name] = (
                self._strategy_consecutive_losses.get(strategy_name, 0) + 1
            )
        else:
            self._strategy_consecutive_losses[strategy_name] = 0

        logger.debug(
            f"Trade recorded: P&L=${pnl}, Strategy={strategy_name}, "
            f"Daily P&L=${self._state.daily_pnl}, Trades today={self._state.trades_today}"
        )

        # Check limits
        self._check_limits()

    def _check_limits(self) -> None:
        """Check all loss limits and trigger if exceeded."""
        if self._state.is_triggered:
            return

        account_value = Decimal(self._settings.paper_trading_capital)

        # Check daily loss limit
        daily_loss_limit = account_value * Decimal(self._settings.max_daily_loss_pct / 100)
        if self._state.daily_pnl <= -daily_loss_limit:
            self._trigger(
                f"Daily loss limit hit: ${abs(self._state.daily_pnl):.2f} "
                f"(limit: ${daily_loss_limit:.2f})",
            )
            self._state.trigger_reason = "daily_loss"
            return

        # Check weekly loss limit
        weekly_loss_limit = account_value * Decimal(self._settings.max_weekly_loss_pct / 100)
        if self._state.weekly_pnl <= -weekly_loss_limit:
            self._trigger(
                f"Weekly loss limit hit: ${abs(self._state.weekly_pnl):.2f} "
                f"(limit: ${weekly_loss_limit:.2f})",
            )
            self._state.trigger_reason = "weekly_loss"
            return

        # Check monthly drawdown
        monthly_limit = account_value * Decimal(self._settings.max_monthly_drawdown_pct / 100)
        if self._state.monthly_pnl <= -monthly_limit:
            self._trigger(
                f"Monthly drawdown limit hit: ${abs(self._state.monthly_pnl):.2f} "
                f"(limit: ${monthly_limit:.2f}). REQUIRES HUMAN REVIEW.",
            )
            self._state.trigger_reason = "monthly_drawdown"
            return

        # Check max trades per day
        if self._state.trades_today >= self._settings.max_trades_per_day:
            self._trigger(
                f"Max trades per day reached: {self._state.trades_today}",
            )
            self._state.trigger_reason = "max_trades"

    def check_strategy_losses(self, strategy_name: str, max_consecutive: int = 5) -> bool:
        """
        Check if a strategy has hit consecutive loss limit.

        Args:
            strategy_name: Name of the strategy
            max_consecutive: Max allowed consecutive losses

        Returns:
            True if strategy should be disabled
        """
        losses = self._strategy_consecutive_losses.get(strategy_name, 0)
        if losses >= max_consecutive:
            logger.warning(
                f"Strategy {strategy_name} hit {losses} consecutive losses - disabling"
            )
            return True
        return False

    def reset_strategy_losses(self, strategy_name: str) -> None:
        """Reset consecutive loss counter for a strategy."""
        self._strategy_consecutive_losses[strategy_name] = 0

    def can_trade(self) -> tuple[bool, str]:
        """
        Check if trading is currently allowed.

        Returns:
            Tuple of (can_trade, reason)
        """
        self._check_daily_reset()
        self._check_weekly_reset()
        self._check_monthly_reset()

        if self._state.is_triggered:
            return False, f"Circuit breaker active: {self._state.trigger_reason}"

        if self._state.trades_today >= self._settings.max_trades_per_day:
            return False, f"Max trades per day ({self._settings.max_trades_per_day}) reached"

        return True, "Trading allowed"

    def manual_reset(self) -> None:
        """Manually reset the circuit breaker (use with caution)."""
        logger.warning("Circuit breaker manually reset")
        self._state = CircuitBreakerState()
        self._strategy_consecutive_losses.clear()

    def get_state(self) -> CircuitBreakerState:
        """Get current circuit breaker state."""
        self._check_daily_reset()
        self._check_weekly_reset()
        self._check_monthly_reset()
        return self._state

    def get_daily_stats(self) -> dict:
        """Get daily trading statistics."""
        self._check_daily_reset()
        return {
            "daily_pnl": float(self._state.daily_pnl),
            "trades_today": self._state.trades_today,
            "max_trades": self._settings.max_trades_per_day,
            "is_triggered": self._state.is_triggered,
            "trigger_reason": self._state.trigger_reason,
        }
