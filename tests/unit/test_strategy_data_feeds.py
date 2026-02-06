"""Unit tests for strategy data feed integration.

Tests that the main agent correctly feeds data to the ORB and Gap and Go
strategies so they can generate signals.
"""

from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
import pytz

from agent.data.streaming import BarData, QuoteData
from agent.strategies.gap_and_go import GapAndGo
from agent.strategies.orb import OpeningRangeBreakout

ET = pytz.timezone("America/New_York")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def orb_strategy():
    """Create an ORB strategy with allowed symbols."""
    return OpeningRangeBreakout(parameters={"allowed_symbols": ["SPY", "QQQ", "IWM"]})


@pytest.fixture
def gap_strategy():
    """Create a Gap and Go strategy with allowed symbols."""
    return GapAndGo(parameters={"allowed_symbols": ["AAPL", "TSLA", "NVDA"]})


def _make_bar(symbol: str, high: Decimal, low: Decimal, ts: datetime | None = None) -> BarData:
    """Helper to create a BarData instance."""
    if ts is None:
        ts = datetime.now(ET)
    return BarData(
        symbol=symbol,
        timestamp=ts,
        open=low,
        high=high,
        low=low,
        close=high,
        volume=100_000,
        vwap=Decimal("450.00"),
    )


def _make_quote(symbol: str, bid: Decimal, ask: Decimal) -> QuoteData:
    """Helper to create a QuoteData instance."""
    return QuoteData(
        symbol=symbol,
        timestamp=datetime.now(ET),
        bid=bid,
        ask=ask,
        bid_size=100,
        ask_size=100,
    )


def _build_agent_stub(strategies, latest_quotes=None, broker=None):
    """Build a minimal TradingAgent-like object for testing feed methods.

    We import the real class and then override internals to avoid
    touching the broker / database / settings during tests.
    """
    from agent.main import TradingAgent

    with patch.object(TradingAgent, "__init__", lambda self: None):
        agent = TradingAgent.__new__(TradingAgent)

    agent._et_tz = ET
    agent._strategies = strategies
    agent._latest_bars = {}
    agent._latest_quotes = latest_quotes or {}
    agent._daily_bars = defaultdict(list)
    agent._broker = broker or MagicMock()
    agent._premarket_gaps_scanned_today = False
    return agent


# ---------------------------------------------------------------------------
# Tests: _feed_opening_range_data
# ---------------------------------------------------------------------------


class TestFeedOpeningRangeData:
    """Tests for _feed_opening_range_data in TradingAgent."""

    def test_feeds_bar_during_range_window(self, orb_strategy):
        """ORB update_opening_range is called when bar arrives during 9:30-9:45."""
        agent = _build_agent_stub([orb_strategy])
        bar = _make_bar("SPY", Decimal("451.00"), Decimal("449.00"))

        # Mock time to be 9:35 AM ET (within range window)
        mock_time = datetime.now(ET).replace(hour=9, minute=35, second=0)
        with patch.object(type(agent), "_get_market_time", return_value=mock_time):
            agent._feed_opening_range_data(bar)

        opening_range = orb_strategy.get_opening_range("SPY")
        assert opening_range is not None
        assert opening_range.high == Decimal("451.00")
        assert opening_range.low == Decimal("449.00")

    def test_does_not_feed_outside_range_window(self, orb_strategy):
        """ORB update_opening_range is NOT called after 9:45 AM."""
        agent = _build_agent_stub([orb_strategy])
        bar = _make_bar("SPY", Decimal("451.00"), Decimal("449.00"))

        # Mock time to be 10:00 AM ET (after range window)
        mock_time = datetime.now(ET).replace(hour=10, minute=0, second=0)
        with patch.object(type(agent), "_get_market_time", return_value=mock_time):
            agent._feed_opening_range_data(bar)

        assert orb_strategy.get_opening_range("SPY") is None

    def test_does_not_feed_before_market_open(self, orb_strategy):
        """ORB update_opening_range is NOT called before 9:30 AM."""
        agent = _build_agent_stub([orb_strategy])
        bar = _make_bar("SPY", Decimal("451.00"), Decimal("449.00"))

        mock_time = datetime.now(ET).replace(hour=9, minute=25, second=0)
        with patch.object(type(agent), "_get_market_time", return_value=mock_time):
            agent._feed_opening_range_data(bar)

        assert orb_strategy.get_opening_range("SPY") is None

    def test_ignores_non_allowed_symbol(self, orb_strategy):
        """Bars for symbols not in allowed_symbols are ignored."""
        agent = _build_agent_stub([orb_strategy])
        bar = _make_bar("AAPL", Decimal("180.00"), Decimal("178.00"))

        mock_time = datetime.now(ET).replace(hour=9, minute=35, second=0)
        with patch.object(type(agent), "_get_market_time", return_value=mock_time):
            agent._feed_opening_range_data(bar)

        assert orb_strategy.get_opening_range("AAPL") is None

    def test_accumulates_range_across_bars(self, orb_strategy):
        """Multiple bars during range window update the high/low correctly."""
        agent = _build_agent_stub([orb_strategy])

        mock_time = datetime.now(ET).replace(hour=9, minute=32, second=0)
        with patch.object(type(agent), "_get_market_time", return_value=mock_time):
            # First bar
            bar1 = _make_bar("SPY", Decimal("450.00"), Decimal("448.00"))
            agent._feed_opening_range_data(bar1)

            # Second bar with higher high
            bar2 = _make_bar("SPY", Decimal("452.00"), Decimal("449.00"))
            agent._feed_opening_range_data(bar2)

            # Third bar with lower low
            bar3 = _make_bar("SPY", Decimal("451.00"), Decimal("447.00"))
            agent._feed_opening_range_data(bar3)

        opening_range = orb_strategy.get_opening_range("SPY")
        assert opening_range is not None
        assert opening_range.high == Decimal("452.00")  # max of all bars
        assert opening_range.low == Decimal("447.00")  # min of all bars

    def test_inactive_strategy_is_skipped(self, orb_strategy):
        """Disabled ORB strategy does not receive data."""
        orb_strategy.disable("testing")
        agent = _build_agent_stub([orb_strategy])
        bar = _make_bar("SPY", Decimal("451.00"), Decimal("449.00"))

        mock_time = datetime.now(ET).replace(hour=9, minute=35, second=0)
        with patch.object(type(agent), "_get_market_time", return_value=mock_time):
            agent._feed_opening_range_data(bar)

        assert orb_strategy.get_opening_range("SPY") is None


# ---------------------------------------------------------------------------
# Tests: _feed_gap_price_action
# ---------------------------------------------------------------------------


class TestFeedGapPriceAction:
    """Tests for _feed_gap_price_action in TradingAgent."""

    def test_feeds_price_action_for_registered_gap(self, gap_strategy):
        """Price action is forwarded for symbols with registered gaps."""
        # Register a gap first
        gap_strategy.register_gap(
            symbol="AAPL",
            previous_close=Decimal("170.00"),
            premarket_price=Decimal("180.00"),
            premarket_volume=500_000,
        )

        agent = _build_agent_stub([gap_strategy])
        bar = _make_bar("AAPL", Decimal("181.00"), Decimal("179.00"))

        mock_time = datetime.now(ET).replace(hour=9, minute=40, second=0)
        with patch.object(type(agent), "_get_market_time", return_value=mock_time):
            agent._feed_gap_price_action(bar)

        assert gap_strategy._entry_prices_today.get("AAPL") is not None
        assert gap_strategy._entry_prices_today["AAPL"]["high"] == Decimal("181.00")
        assert gap_strategy._entry_prices_today["AAPL"]["low"] == Decimal("179.00")

    def test_does_not_feed_without_gap(self, gap_strategy):
        """Price action is NOT forwarded for symbols without registered gaps."""
        agent = _build_agent_stub([gap_strategy])
        bar = _make_bar("AAPL", Decimal("181.00"), Decimal("179.00"))

        mock_time = datetime.now(ET).replace(hour=9, minute=40, second=0)
        with patch.object(type(agent), "_get_market_time", return_value=mock_time):
            agent._feed_gap_price_action(bar)

        assert gap_strategy._entry_prices_today.get("AAPL") is None

    def test_does_not_feed_before_market_open(self, gap_strategy):
        """Price action is NOT forwarded before 9:30 AM."""
        gap_strategy.register_gap(
            symbol="AAPL",
            previous_close=Decimal("170.00"),
            premarket_price=Decimal("180.00"),
            premarket_volume=500_000,
        )

        agent = _build_agent_stub([gap_strategy])
        bar = _make_bar("AAPL", Decimal("181.00"), Decimal("179.00"))

        mock_time = datetime.now(ET).replace(hour=9, minute=25, second=0)
        with patch.object(type(agent), "_get_market_time", return_value=mock_time):
            agent._feed_gap_price_action(bar)

        assert gap_strategy._entry_prices_today.get("AAPL") is None


# ---------------------------------------------------------------------------
# Tests: _scan_premarket_gaps
# ---------------------------------------------------------------------------


class TestScanPremarketGaps:
    """Tests for _scan_premarket_gaps in TradingAgent."""

    @pytest.mark.asyncio
    async def test_registers_qualifying_gap(self, gap_strategy):
        """Symbols with gap >= min_gap_pct are registered."""
        broker = MagicMock()

        # Snapshot returns previous_close, ask price, and volume for each symbol
        def mock_snapshot(symbol):
            data = {
                "AAPL": {
                    "symbol": "AAPL",
                    "previous_close": Decimal("100.00"),
                    "ask": 105.00,
                    "daily_volume": 500_000,
                },
                "TSLA": {
                    "symbol": "TSLA",
                    "previous_close": Decimal("100.00"),
                    "ask": 200.00,
                    "daily_volume": 1_000_000,
                },
                "NVDA": {
                    "symbol": "NVDA",
                    "previous_close": Decimal("100.00"),
                    "ask": 101.00,  # Only 1% gap
                    "daily_volume": 300_000,
                },
            }
            return data.get(symbol)

        broker.get_snapshot.side_effect = mock_snapshot
        broker.get_previous_close.return_value = None  # Fallback shouldn't be needed

        agent = _build_agent_stub([gap_strategy], broker=broker)

        await agent._scan_premarket_gaps()

        assert agent._premarket_gaps_scanned_today is True
        # AAPL and TSLA should have gaps registered (5% and 100%)
        assert gap_strategy.get_gap("AAPL") is not None
        assert gap_strategy.get_gap("TSLA") is not None
        # NVDA has 1% gap — below 3% threshold
        assert gap_strategy.get_gap("NVDA") is None

    @pytest.mark.asyncio
    async def test_skips_when_no_gap_strategy(self):
        """Does nothing when no Gap and Go strategy is active."""
        orb = OpeningRangeBreakout(parameters={"allowed_symbols": ["SPY"]})
        broker = MagicMock()
        agent = _build_agent_stub([orb], broker=broker)

        await agent._scan_premarket_gaps()
        assert agent._premarket_gaps_scanned_today is False

    @pytest.mark.asyncio
    async def test_skips_when_no_allowed_symbols(self, gap_strategy):
        """Does nothing when allowed_symbols is empty."""
        gap_strategy.parameters["allowed_symbols"] = []
        agent = _build_agent_stub([gap_strategy])

        await agent._scan_premarket_gaps()
        assert agent._premarket_gaps_scanned_today is False

    @pytest.mark.asyncio
    async def test_falls_back_to_api_quote(self, gap_strategy):
        """Uses broker.get_latest_quote() when snapshot is unavailable."""
        broker = MagicMock()
        broker.get_snapshot.return_value = None  # No snapshot
        broker.get_previous_close.return_value = Decimal("100.00")
        broker.get_latest_quote.return_value = {
            "symbol": "AAPL",
            "bid": 104.50,
            "ask": 105.00,
        }

        # Override min_premarket_volume to 0 since we can't get volume
        # from quote fallback path
        gap_strategy.parameters["min_premarket_volume"] = 0

        agent = _build_agent_stub([gap_strategy], broker=broker)

        await agent._scan_premarket_gaps()

        assert agent._premarket_gaps_scanned_today is True
        assert gap_strategy.get_gap("AAPL") is not None

    @pytest.mark.asyncio
    async def test_handles_missing_previous_close(self, gap_strategy):
        """Gracefully skips symbols where previous close is unavailable."""
        broker = MagicMock()
        broker.get_snapshot.return_value = None  # No snapshot
        broker.get_previous_close.return_value = None

        agent = _build_agent_stub([gap_strategy], broker=broker)

        await agent._scan_premarket_gaps()

        assert agent._premarket_gaps_scanned_today is True
        assert gap_strategy.get_gap("AAPL") is None

    @pytest.mark.asyncio
    async def test_idempotent_gap_registration(self, gap_strategy):
        """Calling _scan_premarket_gaps multiple times overwrites cleanly."""
        broker = MagicMock()
        broker.get_snapshot.return_value = {
            "symbol": "AAPL",
            "previous_close": Decimal("100.00"),
            "ask": 105.00,
            "daily_volume": 500_000,
        }

        gap_strategy.parameters["allowed_symbols"] = ["AAPL"]

        agent = _build_agent_stub([gap_strategy], broker=broker)

        # Call twice
        await agent._scan_premarket_gaps()
        agent._premarket_gaps_scanned_today = False  # Reset for second call
        await agent._scan_premarket_gaps()

        gap = gap_strategy.get_gap("AAPL")
        assert gap is not None
        assert gap.gap_percent == pytest.approx(5.0, abs=0.1)


# ---------------------------------------------------------------------------
# Tests: _on_bar_data integration
# ---------------------------------------------------------------------------


class TestOnBarDataIntegration:
    """Tests that _on_bar_data correctly routes to strategy feeds."""

    def test_on_bar_data_calls_feed_methods(self, orb_strategy, gap_strategy):
        """_on_bar_data routes bars to both ORB and Gap strategy feeds."""
        agent = _build_agent_stub([orb_strategy, gap_strategy])

        # Register a gap for AAPL so price action feed works
        gap_strategy.register_gap(
            symbol="AAPL",
            previous_close=Decimal("170.00"),
            premarket_price=Decimal("180.00"),
            premarket_volume=500_000,
        )

        mock_time = datetime.now(ET).replace(hour=9, minute=35, second=0)

        with patch.object(type(agent), "_get_market_time", return_value=mock_time):
            # SPY bar should feed to ORB (9:35 is within range window)
            spy_bar = _make_bar("SPY", Decimal("451.00"), Decimal("449.00"))
            agent._on_bar_data(spy_bar)

            # AAPL bar should feed to Gap price action
            aapl_bar = _make_bar("AAPL", Decimal("181.00"), Decimal("179.00"))
            agent._on_bar_data(aapl_bar)

        # ORB should have received the SPY bar
        assert orb_strategy.get_opening_range("SPY") is not None

        # Gap strategy should have received AAPL price action
        assert gap_strategy._entry_prices_today.get("AAPL") is not None

        # Both bars should be in the cache
        assert agent._latest_bars.get("SPY") is not None
        assert agent._latest_bars.get("AAPL") is not None


# ---------------------------------------------------------------------------
# Tests: Gap and Go register_gap
# ---------------------------------------------------------------------------


class TestGapAndGoRegistration:
    """Tests for GapAndGo.register_gap() behavior."""

    def test_register_gap_up(self, gap_strategy):
        """Register a gap-up with sufficient gap percentage."""
        result = gap_strategy.register_gap(
            symbol="AAPL",
            previous_close=Decimal("170.00"),
            premarket_price=Decimal("180.00"),
            premarket_volume=500_000,
        )

        assert result is not None
        assert result.gap_direction == "up"
        assert result.gap_percent == pytest.approx(5.88, abs=0.1)

    def test_register_gap_below_threshold(self, gap_strategy):
        """Gaps below min_gap_pct are rejected."""
        result = gap_strategy.register_gap(
            symbol="AAPL",
            previous_close=Decimal("170.00"),
            premarket_price=Decimal("172.00"),  # ~1.2% gap
            premarket_volume=500_000,
        )

        assert result is None
        assert gap_strategy.get_gap("AAPL") is None

    def test_reset_daily_clears_gaps(self, gap_strategy):
        """Daily reset clears all registered gaps."""
        gap_strategy.register_gap(
            symbol="AAPL",
            previous_close=Decimal("170.00"),
            premarket_price=Decimal("180.00"),
            premarket_volume=500_000,
        )
        assert gap_strategy.get_gap("AAPL") is not None

        gap_strategy.reset_daily()

        assert gap_strategy.get_gap("AAPL") is None


# ---------------------------------------------------------------------------
# Tests: ORB opening range accumulation
# ---------------------------------------------------------------------------


class TestORBRangeAccumulation:
    """Tests for ORB opening range building."""

    def test_range_accumulates_correctly(self):
        """Multiple updates correctly track the overall high and low."""
        strategy = OpeningRangeBreakout()

        strategy.update_opening_range("SPY", Decimal("450.00"), Decimal("448.00"), force=True)
        strategy.update_opening_range("SPY", Decimal("452.00"), Decimal("449.00"), force=True)
        strategy.update_opening_range("SPY", Decimal("451.00"), Decimal("447.00"), force=True)

        opening_range = strategy.get_opening_range("SPY")
        assert opening_range is not None
        assert opening_range.high == Decimal("452.00")
        assert opening_range.low == Decimal("447.00")

    def test_multiple_symbols_independent(self):
        """Opening ranges for different symbols are tracked independently."""
        strategy = OpeningRangeBreakout()

        strategy.update_opening_range("SPY", Decimal("450.00"), Decimal("448.00"), force=True)
        strategy.update_opening_range("QQQ", Decimal("380.00"), Decimal("378.00"), force=True)

        spy_range = strategy.get_opening_range("SPY")
        qqq_range = strategy.get_opening_range("QQQ")

        assert spy_range.high == Decimal("450.00")
        assert qqq_range.high == Decimal("380.00")

    def test_reset_daily_clears_ranges(self):
        """Daily reset clears all opening ranges."""
        strategy = OpeningRangeBreakout()
        strategy.update_opening_range("SPY", Decimal("450.00"), Decimal("448.00"), force=True)

        strategy.reset_daily()

        assert strategy.get_opening_range("SPY") is None
