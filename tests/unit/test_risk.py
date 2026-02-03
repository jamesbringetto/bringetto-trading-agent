"""Unit tests for risk management modules."""

from decimal import Decimal

import pytest

from agent.config.constants import OrderSide
from agent.risk.circuit_breaker import CircuitBreaker
from agent.risk.validator import TradeValidator
from agent.strategies.base import StrategySignal


class TestCircuitBreaker:
    """Tests for the CircuitBreaker class."""

    def test_initialization(self):
        """Test circuit breaker initializes correctly."""
        cb = CircuitBreaker()
        state = cb.get_state()
        assert state.is_triggered is False
        assert state.daily_pnl == Decimal(0)

    def test_record_winning_trade(self):
        """Test recording a winning trade."""
        cb = CircuitBreaker()
        cb.record_trade(Decimal("100.00"), "test_strategy")

        state = cb.get_state()
        assert state.daily_pnl == Decimal("100.00")
        assert state.trades_today == 1

    def test_record_losing_trade(self):
        """Test recording a losing trade."""
        cb = CircuitBreaker()
        cb.record_trade(Decimal("-50.00"), "test_strategy")

        state = cb.get_state()
        assert state.daily_pnl == Decimal("-50.00")
        assert state.trades_today == 1

    def test_can_trade_initially(self):
        """Test that trading is allowed initially."""
        cb = CircuitBreaker()
        can_trade, reason = cb.can_trade()
        assert can_trade is True

    def test_strategy_consecutive_losses(self):
        """Test tracking consecutive losses per strategy."""
        cb = CircuitBreaker()

        # Record 5 losses
        for _ in range(5):
            cb.record_trade(Decimal("-100.00"), "losing_strategy")

        should_disable = cb.check_strategy_losses("losing_strategy", max_consecutive=5)
        assert should_disable is True

    def test_manual_reset(self):
        """Test manual reset of circuit breaker."""
        cb = CircuitBreaker()

        # Record some activity
        cb.record_trade(Decimal("-100.00"), "test_strategy")
        cb.manual_reset()

        state = cb.get_state()
        assert state.daily_pnl == Decimal(0)
        assert state.trades_today == 0


class TestTradeValidator:
    """Tests for the TradeValidator class."""

    @pytest.fixture
    def validator(self):
        """Create a validator instance."""
        return TradeValidator()

    @pytest.fixture
    def valid_signal(self):
        """Create a valid trading signal."""
        return StrategySignal(
            symbol="SPY",
            side=OrderSide.BUY,
            entry_price=Decimal("450.00"),
            stop_loss=Decimal("445.00"),
            take_profit=Decimal("460.00"),
            position_size_pct=10.0,
            confidence=0.7,
            reasoning="Test signal",
        )

    def test_validate_missing_stop_loss(self, validator):
        """Test that signals without stop loss are rejected."""
        signal = StrategySignal(
            symbol="SPY",
            side=OrderSide.BUY,
            entry_price=Decimal("450.00"),
            stop_loss=Decimal("0"),  # Invalid
            take_profit=Decimal("460.00"),
            position_size_pct=10.0,
            confidence=0.7,
            reasoning="Test signal",
        )

        result = validator.validate_signal(
            signal=signal,
            account_value=Decimal("100000"),
            buying_power=Decimal("50000"),
            current_positions=0,
            current_positions_value=Decimal("0"),
        )

        assert result.is_valid is False
        assert "stop loss" in result.reason.lower()

    def test_validate_invalid_stop_loss_direction(self, validator):
        """Test that stop loss in wrong direction is rejected."""
        signal = StrategySignal(
            symbol="SPY",
            side=OrderSide.BUY,
            entry_price=Decimal("450.00"),
            stop_loss=Decimal("455.00"),  # Above entry for BUY - invalid
            take_profit=Decimal("460.00"),
            position_size_pct=10.0,
            confidence=0.7,
            reasoning="Test signal",
        )

        result = validator.validate_signal(
            signal=signal,
            account_value=Decimal("100000"),
            buying_power=Decimal("50000"),
            current_positions=0,
            current_positions_value=Decimal("0"),
        )

        assert result.is_valid is False

    def test_validate_insufficient_buying_power(self, validator, valid_signal):
        """Test that insufficient buying power is rejected."""
        result = validator.validate_signal(
            signal=valid_signal,
            account_value=Decimal("100000"),
            buying_power=Decimal("5000"),  # Only $5k available
            current_positions=0,
            current_positions_value=Decimal("0"),
        )

        assert result.is_valid is False
        assert "buying power" in result.reason.lower()

    def test_validate_max_positions_reached(self, validator, valid_signal):
        """Test that max positions limit is enforced."""
        result = validator.validate_signal(
            signal=valid_signal,
            account_value=Decimal("100000"),
            buying_power=Decimal("50000"),
            current_positions=10,  # Max is 10
            current_positions_value=Decimal("50000"),
        )

        assert result.is_valid is False
        assert "max" in result.reason.lower() and "position" in result.reason.lower()

    def test_can_trade_symbol_blacklist(self, validator):
        """Test that blacklisted symbols are rejected."""
        can_trade, reason = validator.can_trade_symbol("TQQQ")
        assert can_trade is False
        assert "blacklist" in reason.lower()

    def test_can_trade_symbol_allowed(self, validator):
        """Test that allowed symbols pass."""
        can_trade, reason = validator.can_trade_symbol("SPY")
        assert can_trade is True
