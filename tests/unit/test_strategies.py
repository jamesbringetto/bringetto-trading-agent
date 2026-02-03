"""Unit tests for trading strategies."""

from decimal import Decimal
from datetime import datetime

import pytest

from agent.config.constants import OrderSide
from agent.strategies.base import MarketContext, StrategySignal
from agent.strategies.orb import OpeningRangeBreakout
from agent.strategies.vwap_reversion import VWAPReversion


@pytest.fixture
def sample_context():
    """Create a sample market context for testing."""
    return MarketContext(
        symbol="SPY",
        current_price=Decimal("450.00"),
        open_price=Decimal("448.00"),
        high_price=Decimal("451.00"),
        low_price=Decimal("447.50"),
        volume=50_000_000,
        vwap=Decimal("449.50"),
        rsi=45.0,
        macd=0.5,
        macd_signal=0.3,
        ma_50=Decimal("448.00"),
    )


class TestOpeningRangeBreakout:
    """Tests for the Opening Range Breakout strategy."""

    def test_initialization(self):
        """Test strategy initializes with correct defaults."""
        strategy = OpeningRangeBreakout()
        assert strategy.name == "Opening Range Breakout"
        assert strategy.is_active is True
        assert "SPY" in strategy.parameters["allowed_symbols"]

    def test_update_opening_range(self):
        """Test opening range is tracked correctly."""
        strategy = OpeningRangeBreakout()
        strategy.update_opening_range("SPY", Decimal("450.00"), Decimal("448.00"))

        opening_range = strategy.get_opening_range("SPY")
        assert opening_range is not None
        assert opening_range.high == Decimal("450.00")
        assert opening_range.low == Decimal("448.00")

    def test_validate_entry_checks_min_price(self, sample_context):
        """Test that validation rejects low-priced stocks."""
        strategy = OpeningRangeBreakout()
        low_price_context = MarketContext(
            symbol="PENNY",
            current_price=Decimal("3.50"),  # Below $5 minimum
            open_price=Decimal("3.40"),
            high_price=Decimal("3.60"),
            low_price=Decimal("3.30"),
            volume=1_000_000,
        )
        strategy.parameters["min_price"] = 5.0

        is_valid, reason = strategy.validate_entry(low_price_context)
        assert is_valid is False
        assert "minimum" in reason.lower()


class TestVWAPReversion:
    """Tests for the VWAP Mean Reversion strategy."""

    def test_initialization(self):
        """Test strategy initializes correctly."""
        strategy = VWAPReversion()
        assert strategy.name == "VWAP Mean Reversion"
        assert strategy.is_active is True

    def test_calculate_vwap_deviation(self):
        """Test VWAP deviation calculation."""
        strategy = VWAPReversion()
        deviation = strategy._calculate_vwap_deviation(
            Decimal("451.50"), Decimal("450.00")
        )
        assert abs(deviation - 0.333) < 0.01  # ~0.33% above VWAP

    def test_no_signal_without_vwap(self, sample_context):
        """Test that no signal is generated without VWAP data."""
        strategy = VWAPReversion()
        context_no_vwap = MarketContext(
            symbol="AAPL",
            current_price=Decimal("180.00"),
            open_price=Decimal("179.00"),
            high_price=Decimal("181.00"),
            low_price=Decimal("178.50"),
            volume=20_000_000,
            vwap=None,  # No VWAP
            rsi=35.0,
        )

        signal = strategy.should_enter(context_no_vwap)
        assert signal is None


class TestStrategySignal:
    """Tests for the StrategySignal class."""

    def test_risk_reward_ratio_buy(self):
        """Test risk/reward ratio calculation for buy."""
        signal = StrategySignal(
            symbol="SPY",
            side=OrderSide.BUY,
            entry_price=Decimal("450.00"),
            stop_loss=Decimal("445.00"),  # $5 risk
            take_profit=Decimal("460.00"),  # $10 reward
            position_size_pct=10.0,
            confidence=0.7,
            reasoning="Test signal",
        )

        assert signal.risk_reward_ratio == 2.0  # 10/5 = 2

    def test_risk_reward_ratio_sell(self):
        """Test risk/reward ratio calculation for sell."""
        signal = StrategySignal(
            symbol="SPY",
            side=OrderSide.SELL,
            entry_price=Decimal("450.00"),
            stop_loss=Decimal("455.00"),  # $5 risk
            take_profit=Decimal("440.00"),  # $10 reward
            position_size_pct=10.0,
            confidence=0.7,
            reasoning="Test signal",
        )

        assert signal.risk_reward_ratio == 2.0

    def test_signal_to_dict(self):
        """Test signal serialization to dictionary."""
        signal = StrategySignal(
            symbol="SPY",
            side=OrderSide.BUY,
            entry_price=Decimal("450.00"),
            stop_loss=Decimal("445.00"),
            take_profit=Decimal("460.00"),
            position_size_pct=10.0,
            confidence=0.7,
            reasoning="Test signal",
            indicators={"rsi": 35.0},
        )

        data = signal.to_dict()
        assert data["symbol"] == "SPY"
        assert data["side"] == "buy"
        assert data["confidence"] == 0.7
        assert data["indicators"]["rsi"] == 35.0
