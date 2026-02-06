"""Position sizing calculator with risk management."""

from dataclasses import dataclass
from decimal import Decimal

from loguru import logger

from agent.config.settings import get_settings


@dataclass
class PositionSize:
    """Calculated position size."""

    shares: Decimal
    dollar_amount: Decimal
    risk_amount: Decimal
    position_pct: float
    is_valid: bool
    rejection_reason: str | None = None


class PositionSizer:
    """
    Position sizing calculator based on risk parameters.

    Supports multiple sizing methods:
    - Fixed percentage of portfolio
    - Risk-based (based on stop loss distance)
    - Kelly Criterion (optional)
    """

    def __init__(self):
        self._settings = get_settings()

    def calculate_fixed_percentage(
        self,
        account_value: Decimal,
        current_price: Decimal,
        position_pct: float,
    ) -> PositionSize:
        """
        Calculate position size based on fixed percentage of portfolio.

        Args:
            account_value: Current account value
            current_price: Current stock price
            position_pct: Percentage of portfolio for this position
        """
        # Validate inputs
        if account_value <= 0 or current_price <= 0:
            return PositionSize(
                shares=Decimal(0),
                dollar_amount=Decimal(0),
                risk_amount=Decimal(0),
                position_pct=0,
                is_valid=False,
                rejection_reason="Invalid account value or price",
            )

        # Check max position size limit
        max_pct = self._settings.max_position_size_pct
        if position_pct > max_pct:
            logger.warning(f"Position size {position_pct}% exceeds max {max_pct}%, capping")
            position_pct = max_pct

        # Calculate dollar amount
        dollar_amount = account_value * Decimal(position_pct / 100)

        # Calculate shares (round down to whole shares)
        shares = (dollar_amount / current_price).quantize(Decimal("1"))

        # Recalculate actual dollar amount
        actual_dollar_amount = shares * current_price
        actual_pct = float(actual_dollar_amount / account_value) * 100

        return PositionSize(
            shares=shares,
            dollar_amount=actual_dollar_amount,
            risk_amount=Decimal(0),  # Not calculated in fixed percentage mode
            position_pct=actual_pct,
            is_valid=shares > 0,
            rejection_reason=None if shares > 0 else "Position too small",
        )

    def calculate_risk_based(
        self,
        account_value: Decimal,
        current_price: Decimal,
        stop_loss_price: Decimal,
        risk_pct: float | None = None,
    ) -> PositionSize:
        """
        Calculate position size based on risk (stop loss distance).

        This ensures that if stop loss is hit, the loss equals the specified
        percentage of the portfolio.

        Args:
            account_value: Current account value
            current_price: Current stock price
            stop_loss_price: Stop loss price
            risk_pct: Risk percentage per trade (defaults to settings)
        """
        if risk_pct is None:
            risk_pct = self._settings.max_risk_per_trade_pct

        # Validate inputs
        if account_value <= 0 or current_price <= 0:
            return PositionSize(
                shares=Decimal(0),
                dollar_amount=Decimal(0),
                risk_amount=Decimal(0),
                position_pct=0,
                is_valid=False,
                rejection_reason="Invalid account value or price",
            )

        # Calculate risk per share
        risk_per_share = abs(current_price - stop_loss_price)
        if risk_per_share <= 0:
            return PositionSize(
                shares=Decimal(0),
                dollar_amount=Decimal(0),
                risk_amount=Decimal(0),
                position_pct=0,
                is_valid=False,
                rejection_reason="Stop loss equals entry price",
            )

        # Calculate max risk amount
        max_risk_amount = account_value * Decimal(risk_pct / 100)

        # Calculate shares based on risk
        shares = (max_risk_amount / risk_per_share).quantize(Decimal("1"))

        # Calculate dollar amount
        dollar_amount = shares * current_price

        # Check if position exceeds max position size
        max_position = account_value * Decimal(self._settings.max_position_size_pct / 100)
        if dollar_amount > max_position:
            shares = (max_position / current_price).quantize(Decimal("1"))
            dollar_amount = shares * current_price
            logger.warning(f"Risk-based size ${dollar_amount} exceeds max position, capping")

        position_pct = float(dollar_amount / account_value) * 100
        actual_risk = shares * risk_per_share

        return PositionSize(
            shares=shares,
            dollar_amount=dollar_amount,
            risk_amount=actual_risk,
            position_pct=position_pct,
            is_valid=shares > 0,
            rejection_reason=None if shares > 0 else "Position too small for risk level",
        )

    def validate_position(
        self,
        position_size: PositionSize,
        account_value: Decimal,
        current_positions_value: Decimal,
    ) -> tuple[bool, str]:
        """
        Validate a position against portfolio limits.

        Args:
            position_size: Calculated position size
            account_value: Current account value
            current_positions_value: Total value of current positions
        """
        if not position_size.is_valid:
            return False, position_size.rejection_reason or "Invalid position"

        # Check position size limit
        max_position_pct = self._settings.max_position_size_pct
        if position_size.position_pct > max_position_pct:
            return (
                False,
                f"Position {position_size.position_pct:.1f}% exceeds limit {max_position_pct}%",
            )

        # Check total exposure limit (60% max deployed)
        max_deployed_pct = 60.0  # Hardcoded from requirements
        new_total = current_positions_value + position_size.dollar_amount
        new_deployed_pct = float(new_total / account_value) * 100

        if new_deployed_pct > max_deployed_pct:
            return (
                False,
                f"Total exposure {new_deployed_pct:.1f}% would exceed limit {max_deployed_pct}%",
            )

        return True, "Position valid"

    def adjust_for_volatility(
        self,
        base_size: PositionSize,
        atr: float,
        avg_atr: float,
    ) -> PositionSize:
        """
        Adjust position size based on current volatility.

        Reduces position size when volatility is high, increases when low.

        Args:
            base_size: Base calculated position size
            atr: Current ATR
            avg_atr: Average ATR (baseline)
        """
        if avg_atr <= 0 or atr <= 0:
            return base_size

        # Calculate volatility ratio
        vol_ratio = atr / avg_atr

        # Adjust factor (inverse relationship)
        # High volatility = smaller position, low volatility = larger position
        # Cap adjustment between 0.5x and 1.5x
        adjustment = min(1.5, max(0.5, 1.0 / vol_ratio))

        adjusted_shares = (base_size.shares * Decimal(adjustment)).quantize(Decimal("1"))

        if adjusted_shares < 1:
            return PositionSize(
                shares=Decimal(0),
                dollar_amount=Decimal(0),
                risk_amount=Decimal(0),
                position_pct=0,
                is_valid=False,
                rejection_reason="Volatility adjustment resulted in zero shares",
            )

        # Recalculate other fields
        share_ratio = adjusted_shares / base_size.shares if base_size.shares > 0 else Decimal(0)

        return PositionSize(
            shares=adjusted_shares,
            dollar_amount=base_size.dollar_amount * share_ratio,
            risk_amount=base_size.risk_amount * share_ratio,
            position_pct=base_size.position_pct * float(share_ratio),
            is_valid=True,
            rejection_reason=None,
        )
