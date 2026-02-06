"""Tests verifying all five strategies can generate entry signals.

Each test constructs market conditions that SHOULD trigger a signal,
then asserts the signal is actually produced.  This catches threshold
regressions and missing-data guard-clause bugs.
"""

from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

import pytz

from agent.config.constants import OrderSide
from agent.strategies.base import MarketContext
from agent.strategies.eod_reversal import EODReversal
from agent.strategies.gap_and_go import GapAndGo
from agent.strategies.momentum_scalp import MomentumScalp
from agent.strategies.orb import OpeningRangeBreakout
from agent.strategies.vwap_reversion import VWAPReversion

ET = pytz.timezone("America/New_York")


def _make_context(
    symbol: str = "SPY",
    price: str = "450.00",
    volume: int = 5_000_000,
    vwap: str | None = "449.50",
    rsi: float | None = 45.0,
    macd: float | None = 0.5,
    macd_signal: float | None = 0.3,
    ma_50: str | None = "448.00",
) -> MarketContext:
    """Helper to build a MarketContext with sensible defaults."""
    return MarketContext(
        symbol=symbol,
        current_price=Decimal(price),
        open_price=Decimal("448.00"),
        high_price=Decimal("451.00"),
        low_price=Decimal("447.50"),
        volume=volume,
        vwap=Decimal(vwap) if vwap else None,
        rsi=rsi,
        macd=macd,
        macd_signal=macd_signal,
        ma_50=Decimal(ma_50) if ma_50 else None,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Opening Range Breakout
# ─────────────────────────────────────────────────────────────────────────────
class TestORBSignalGeneration:
    """Verify ORB generates signals when conditions are met."""

    def _make_orb(self) -> OpeningRangeBreakout:
        strategy = OpeningRangeBreakout(parameters={"allowed_symbols": ["SPY", "QQQ", "IWM"]})
        # Set an opening range: high 450, low 448
        strategy.update_opening_range("SPY", Decimal("450.00"), Decimal("448.00"), force=True)
        return strategy

    def test_breakout_above_range_generates_buy(self):
        """Price above opening range high should produce a BUY signal."""
        strategy = self._make_orb()
        # Price above breakout level (450 * 1.001 = 450.45)
        context = _make_context(symbol="SPY", price="451.00")

        # Mock time to be in ORB trading period (e.g. 10:00 AM ET)
        fake_time = ET.localize(datetime(2025, 1, 15, 10, 0, 0))
        with patch.object(strategy, "_get_market_time", return_value=fake_time):
            signal = strategy.should_enter(context)

        assert signal is not None
        assert signal.side == OrderSide.BUY
        assert signal.symbol == "SPY"

    def test_breakdown_below_range_generates_sell(self):
        """Price below opening range low should produce a SELL signal."""
        strategy = self._make_orb()
        # Price below breakdown level (448 * 0.999 = 447.552)
        context = _make_context(symbol="SPY", price="447.00")

        fake_time = ET.localize(datetime(2025, 1, 15, 10, 0, 0))
        with patch.object(strategy, "_get_market_time", return_value=fake_time):
            signal = strategy.should_enter(context)

        assert signal is not None
        assert signal.side == OrderSide.SELL
        assert signal.symbol == "SPY"

    def test_no_signal_without_opening_range(self):
        """Without an established range, no signal should be generated."""
        strategy = OpeningRangeBreakout(parameters={"allowed_symbols": ["SPY"]})
        # No range established
        context = _make_context(symbol="SPY", price="451.00")

        fake_time = ET.localize(datetime(2025, 1, 15, 10, 0, 0))
        with patch.object(strategy, "_get_market_time", return_value=fake_time):
            signal = strategy.should_enter(context)

        assert signal is None

    def test_no_signal_during_range_period(self):
        """During the range collection period (before 9:45), no signal."""
        strategy = self._make_orb()
        context = _make_context(symbol="SPY", price="451.00")

        # 9:40 AM — still in range period
        fake_time = ET.localize(datetime(2025, 1, 15, 9, 40, 0))
        with patch.object(strategy, "_get_market_time", return_value=fake_time):
            signal = strategy.should_enter(context)

        assert signal is None

    def test_no_signal_price_within_range(self):
        """Price inside the range should not trigger a signal."""
        strategy = self._make_orb()
        context = _make_context(symbol="SPY", price="449.00")  # Between 448 and 450

        fake_time = ET.localize(datetime(2025, 1, 15, 10, 0, 0))
        with patch.object(strategy, "_get_market_time", return_value=fake_time):
            signal = strategy.should_enter(context)

        assert signal is None


# ─────────────────────────────────────────────────────────────────────────────
# 2. VWAP Mean Reversion
# ─────────────────────────────────────────────────────────────────────────────
class TestVWAPReversionSignalGeneration:
    """Verify VWAP Reversion generates signals when conditions are met."""

    def _make_vwap(self) -> VWAPReversion:
        return VWAPReversion(parameters={"allowed_symbols": ["AAPL", "MSFT", "NVDA"]})

    def test_oversold_generates_buy(self):
        """Price far below VWAP with low RSI should produce BUY."""
        strategy = self._make_vwap()
        # Price 1.5% below VWAP (VWAP=200, price≈197) and RSI=30
        context = _make_context(
            symbol="AAPL",
            price="197.00",
            vwap="200.00",
            rsi=30.0,  # At oversold threshold (35 for paper)
        )

        signal = strategy.should_enter(context)
        assert signal is not None
        assert signal.side == OrderSide.BUY
        assert signal.symbol == "AAPL"

    def test_overbought_generates_sell(self):
        """Price far above VWAP with high RSI should produce SELL."""
        strategy = self._make_vwap()
        # Price 1.5% above VWAP (VWAP=200, price≈203) and RSI=70
        context = _make_context(
            symbol="MSFT",
            price="203.00",
            vwap="200.00",
            rsi=70.0,  # At overbought threshold (65 for paper)
        )

        signal = strategy.should_enter(context)
        assert signal is not None
        assert signal.side == OrderSide.SELL
        assert signal.symbol == "MSFT"

    def test_no_signal_small_deviation(self):
        """Small deviation from VWAP should not trigger."""
        strategy = self._make_vwap()
        # Only 0.5% deviation — below 1.0% threshold
        context = _make_context(
            symbol="AAPL",
            price="199.00",
            vwap="200.00",
            rsi=30.0,
        )

        signal = strategy.should_enter(context)
        assert signal is None

    def test_no_signal_without_indicators(self):
        """Missing VWAP or RSI should return None, not crash."""
        strategy = self._make_vwap()
        context = _make_context(symbol="AAPL", vwap=None, rsi=None)

        signal = strategy.should_enter(context)
        assert signal is None


# ─────────────────────────────────────────────────────────────────────────────
# 3. Momentum Scalp
# ─────────────────────────────────────────────────────────────────────────────
class TestMomentumScalpSignalGeneration:
    """Verify Momentum Scalp generates signals on MACD crossovers."""

    def _make_momentum(self) -> MomentumScalp:
        return MomentumScalp(parameters={"allowed_symbols": ["TSLA", "NVDA"]})

    def test_bullish_crossover_generates_buy(self):
        """Bullish MACD crossover with price above MA50 should produce BUY."""
        strategy = self._make_momentum()

        # First evaluation: establish prior state (MACD below signal)
        context_before = _make_context(
            symbol="TSLA",
            price="250.00",
            macd=-0.5,
            macd_signal=0.1,
            rsi=50.0,
            ma_50="245.00",
        )
        signal1 = strategy.should_enter(context_before)
        assert signal1 is None  # First eval establishes state, no crossover

        # Second evaluation: MACD crosses above signal (bullish crossover)
        context_after = _make_context(
            symbol="TSLA",
            price="250.00",
            macd=0.5,
            macd_signal=0.1,
            rsi=50.0,
            ma_50="245.00",
        )
        signal2 = strategy.should_enter(context_after)
        assert signal2 is not None
        assert signal2.side == OrderSide.BUY
        assert signal2.symbol == "TSLA"

    def test_bearish_crossover_generates_sell(self):
        """Bearish MACD crossover with price below MA50 should produce SELL."""
        strategy = self._make_momentum()

        # First evaluation: MACD above signal
        context_before = _make_context(
            symbol="NVDA",
            price="100.00",
            macd=0.5,
            macd_signal=0.1,
            rsi=50.0,
            ma_50="105.00",  # Price below MA50
        )
        strategy.should_enter(context_before)

        # Second evaluation: MACD crosses below signal (bearish crossover)
        context_after = _make_context(
            symbol="NVDA",
            price="100.00",
            macd=-0.5,
            macd_signal=0.1,
            rsi=50.0,
            ma_50="105.00",
        )
        signal = strategy.should_enter(context_after)
        assert signal is not None
        assert signal.side == OrderSide.SELL
        assert signal.symbol == "NVDA"

    def test_no_signal_without_crossover(self):
        """No state change in MACD should not trigger."""
        strategy = self._make_momentum()

        # Both evaluations: MACD above signal (no crossover)
        context1 = _make_context(symbol="TSLA", macd=0.5, macd_signal=0.1, rsi=50.0, ma_50="445.00")
        strategy.should_enter(context1)

        context2 = _make_context(symbol="TSLA", macd=0.6, macd_signal=0.1, rsi=50.0, ma_50="445.00")
        signal = strategy.should_enter(context2)
        assert signal is None

    def test_no_signal_rsi_out_of_range(self):
        """RSI outside the neutral range should reject."""
        strategy = self._make_momentum()

        # Establish state
        context_before = _make_context(
            symbol="TSLA", macd=-0.5, macd_signal=0.1, rsi=80.0, ma_50="445.00"
        )
        strategy.should_enter(context_before)

        # RSI=80 is above the 65 max — should be rejected
        context_after = _make_context(
            symbol="TSLA", macd=0.5, macd_signal=0.1, rsi=80.0, ma_50="445.00"
        )
        signal = strategy.should_enter(context_after)
        assert signal is None

    def test_no_signal_missing_indicators(self):
        """Missing MACD/RSI/MA50 should return None."""
        strategy = self._make_momentum()
        context = _make_context(symbol="TSLA", macd=None, rsi=None, ma_50=None)

        signal = strategy.should_enter(context)
        assert signal is None


# ─────────────────────────────────────────────────────────────────────────────
# 4. Gap and Go
# ─────────────────────────────────────────────────────────────────────────────
class TestGapAndGoSignalGeneration:
    """Verify Gap and Go generates signals on pullback entries."""

    def _make_gap(self) -> GapAndGo:
        strategy = GapAndGo(parameters={"allowed_symbols": ["AAPL", "NVDA"]})
        return strategy

    def test_gap_up_pullback_generates_buy(self):
        """Gap-up stock that pulls back should produce BUY."""
        strategy = self._make_gap()

        # Register a gap (5% up from $190 to $199.50)
        strategy.register_gap(
            symbol="AAPL",
            previous_close=Decimal("190.00"),
            premarket_price=Decimal("199.50"),
            premarket_volume=100_000,
        )

        # Simulate post-open price action — day high was 200
        strategy.update_price_action("AAPL", Decimal("200.00"), Decimal("198.00"))

        # Current price has pulled back ~0.5% from day high (200 → 199)
        context = _make_context(symbol="AAPL", price="199.00")

        # Mock time to be in gap trading window (9:35-10:30 AM)
        fake_time = ET.localize(datetime(2025, 1, 15, 9, 40, 0))
        with patch.object(strategy, "_get_market_time", return_value=fake_time):
            signal = strategy.should_enter(context)

        assert signal is not None
        assert signal.side == OrderSide.BUY
        assert signal.symbol == "AAPL"

    def test_gap_down_pullback_generates_sell(self):
        """Gap-down stock that pulls back should produce SELL."""
        strategy = self._make_gap()

        # Register a down gap (5% down from $200 to $190)
        strategy.register_gap(
            symbol="NVDA",
            previous_close=Decimal("200.00"),
            premarket_price=Decimal("190.00"),
            premarket_volume=100_000,
        )

        # Simulate price action — day low was 189
        strategy.update_price_action("NVDA", Decimal("192.00"), Decimal("189.00"))

        # Price pulled back up ~0.5% from day low (189 → 189.95)
        context = _make_context(symbol="NVDA", price="189.50")

        fake_time = ET.localize(datetime(2025, 1, 15, 9, 40, 0))
        with patch.object(strategy, "_get_market_time", return_value=fake_time):
            signal = strategy.should_enter(context)

        assert signal is not None
        assert signal.side == OrderSide.SELL
        assert signal.symbol == "NVDA"

    def test_no_signal_without_gap_registered(self):
        """Without a registered gap, no signal should be generated."""
        strategy = self._make_gap()
        context = _make_context(symbol="AAPL", price="199.00")

        fake_time = ET.localize(datetime(2025, 1, 15, 9, 40, 0))
        with patch.object(strategy, "_get_market_time", return_value=fake_time):
            signal = strategy.should_enter(context)

        assert signal is None

    def test_no_signal_without_price_action(self):
        """Without post-open price action, no pullback detection possible."""
        strategy = self._make_gap()
        strategy.register_gap(
            symbol="AAPL",
            previous_close=Decimal("190.00"),
            premarket_price=Decimal("199.50"),
            premarket_volume=100_000,
        )
        # No update_price_action() called
        context = _make_context(symbol="AAPL", price="199.00")

        fake_time = ET.localize(datetime(2025, 1, 15, 9, 40, 0))
        with patch.object(strategy, "_get_market_time", return_value=fake_time):
            signal = strategy.should_enter(context)

        assert signal is None

    def test_no_signal_outside_trading_window(self):
        """After 10:30 AM, Gap and Go should not generate signals."""
        strategy = self._make_gap()
        strategy.register_gap(
            symbol="AAPL",
            previous_close=Decimal("190.00"),
            premarket_price=Decimal("199.50"),
            premarket_volume=100_000,
        )
        strategy.update_price_action("AAPL", Decimal("200.00"), Decimal("198.00"))

        context = _make_context(symbol="AAPL", price="199.00")

        # 11:00 AM — past the 10:30 AM exit window
        fake_time = ET.localize(datetime(2025, 1, 15, 11, 0, 0))
        with patch.object(strategy, "_get_market_time", return_value=fake_time):
            signal = strategy.should_enter(context)

        assert signal is None


# ─────────────────────────────────────────────────────────────────────────────
# 5. EOD Reversal
# ─────────────────────────────────────────────────────────────────────────────
class TestEODReversalSignalGeneration:
    """Verify EOD Reversal generates signals in the final hour."""

    def _make_eod(self) -> EODReversal:
        return EODReversal(parameters={"allowed_symbols": ["SPY", "QQQ"]})

    def test_overbought_reversal_generates_sell(self):
        """Overbought in uptrend during EOD window should produce SELL."""
        strategy = self._make_eod()
        # Price 2% above VWAP, RSI=75 (overbought), uptrend
        context = _make_context(
            symbol="SPY",
            price="204.00",
            vwap="200.00",
            rsi=75.0,
        )

        # 3:15 PM ET — in the EOD window
        fake_time = ET.localize(datetime(2025, 1, 15, 15, 15, 0))
        with patch.object(strategy, "_get_market_time", return_value=fake_time):
            signal = strategy.should_enter(context)

        assert signal is not None
        assert signal.side == OrderSide.SELL
        assert signal.symbol == "SPY"

    def test_oversold_reversal_generates_buy(self):
        """Oversold in downtrend during EOD window should produce BUY."""
        strategy = self._make_eod()
        # Price 2% below VWAP, RSI=25 (oversold), downtrend
        context = _make_context(
            symbol="QQQ",
            price="196.00",
            vwap="200.00",
            rsi=25.0,
        )

        fake_time = ET.localize(datetime(2025, 1, 15, 15, 15, 0))
        with patch.object(strategy, "_get_market_time", return_value=fake_time):
            signal = strategy.should_enter(context)

        assert signal is not None
        assert signal.side == OrderSide.BUY
        assert signal.symbol == "QQQ"

    def test_no_signal_outside_eod_window(self):
        """Before 3:00 PM, no EOD signals should be generated."""
        strategy = self._make_eod()
        context = _make_context(
            symbol="SPY",
            price="204.00",
            vwap="200.00",
            rsi=75.0,
        )

        # 2:00 PM — before the EOD window
        fake_time = ET.localize(datetime(2025, 1, 15, 14, 0, 0))
        with patch.object(strategy, "_get_market_time", return_value=fake_time):
            signal = strategy.should_enter(context)

        assert signal is None

    def test_no_signal_rsi_not_extreme(self):
        """RSI in normal range should not trigger EOD reversal."""
        strategy = self._make_eod()
        context = _make_context(
            symbol="SPY",
            price="204.00",
            vwap="200.00",
            rsi=55.0,  # Neutral RSI
        )

        fake_time = ET.localize(datetime(2025, 1, 15, 15, 15, 0))
        with patch.object(strategy, "_get_market_time", return_value=fake_time):
            signal = strategy.should_enter(context)

        assert signal is None

    def test_no_signal_without_indicators(self):
        """Missing RSI or VWAP should return None."""
        strategy = self._make_eod()
        context = _make_context(symbol="SPY", vwap=None, rsi=None)

        fake_time = ET.localize(datetime(2025, 1, 15, 15, 15, 0))
        with patch.object(strategy, "_get_market_time", return_value=fake_time):
            signal = strategy.should_enter(context)

        assert signal is None
