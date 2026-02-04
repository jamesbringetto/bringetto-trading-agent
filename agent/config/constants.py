"""Trading constants and enums."""

from dataclasses import dataclass
from enum import Enum


class StrategyType(str, Enum):
    """Trading strategy types."""

    ORB = "orb"
    VWAP_REVERSION = "vwap_reversion"
    MOMENTUM_SCALP = "momentum_scalp"
    GAP_AND_GO = "gap_and_go"
    EOD_REVERSAL = "eod_reversal"
    EXPERIMENTAL = "experimental"


class OrderSide(str, Enum):
    """Order side."""

    BUY = "buy"
    SELL = "sell"


class OrderStatus(str, Enum):
    """Order status from broker."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class TradeStatus(str, Enum):
    """Internal trade status."""

    OPEN = "open"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class DecisionType(str, Enum):
    """Trade decision type."""

    ENTRY = "entry"
    EXIT = "exit"
    HOLD = "hold"


class MarketRegime(str, Enum):
    """Market regime classification."""

    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    VOLATILE = "volatile"


class AlertSeverity(str, Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class TradingSession(str, Enum):
    """Trading session types for 24/5 trading.

    Per Alpaca 24/5 trading:
    - Overnight: 8:00 PM to 4:00 AM ET
    - Pre-market: 4:00 AM to 9:30 AM ET
    - Regular: 9:30 AM to 4:00 PM ET
    - After-hours: 4:00 PM to 8:00 PM ET
    """

    OVERNIGHT = "overnight"
    PRE_MARKET = "pre_market"
    REGULAR = "regular"
    AFTER_HOURS = "after_hours"


@dataclass(frozen=True)
class TradingConstants:
    """Trading constants and limits."""

    # Asset Tiers
    TIER_1_ASSETS: tuple[str, ...] = ("SPY", "QQQ", "IWM")
    TIER_2_ASSETS: tuple[str, ...] = (
        "AAPL", "MSFT", "NVDA", "TSLA", "GOOGL", "AMZN", "META"
    )

    # Minimum requirements
    MIN_STOCK_PRICE: float = 5.0
    MIN_DAILY_VOLUME: int = 5_000_000
    MAX_BID_ASK_SPREAD_PCT: float = 0.1

    # Strategy-specific position sizes (% of capital)
    ORB_POSITION_SIZE_PCT: float = 10.0
    VWAP_POSITION_SIZE_PCT: float = 8.0
    MOMENTUM_POSITION_SIZE_PCT: float = 5.0
    GAP_POSITION_SIZE_PCT: float = 15.0
    EOD_POSITION_SIZE_PCT: float = 10.0

    # Strategy-specific max concurrent positions
    ORB_MAX_POSITIONS: int = 3
    VWAP_MAX_POSITIONS: int = 4
    MOMENTUM_MAX_POSITIONS: int = 5
    GAP_MAX_POSITIONS: int = 2
    EOD_MAX_POSITIONS: int = 2

    # Auto-disable thresholds
    MAX_CONSECUTIVE_LOSSES: int = 5
    MIN_WIN_RATE_THRESHOLD: float = 0.40
    MIN_PROFIT_FACTOR: float = 0.8
    MIN_TRADES_FOR_EVALUATION: int = 20

    # Circuit breaker cooldowns (in seconds)
    STRATEGY_PAUSE_DURATION: int = 86400  # 1 day
    DAILY_LOSS_COOLDOWN: int = 0  # Until next trading day

    # Time constants
    MARKET_TIMEZONE: str = "America/New_York"
    PRE_MARKET_START_HOUR: int = 4
    AFTER_HOURS_END_HOUR: int = 20

    # 24/5 Trading Session Times (ET)
    # Overnight: 8:00 PM to 4:00 AM ET
    OVERNIGHT_START_HOUR: int = 20  # 8:00 PM
    OVERNIGHT_END_HOUR: int = 4     # 4:00 AM
    # Pre-market: 4:00 AM to 9:30 AM ET
    PRE_MARKET_END_HOUR: int = 9
    PRE_MARKET_END_MINUTE: int = 30
    # Regular: 9:30 AM to 4:00 PM ET
    REGULAR_START_HOUR: int = 9
    REGULAR_START_MINUTE: int = 30
    REGULAR_END_HOUR: int = 16
    # After-hours: 4:00 PM to 8:00 PM ET
    AFTER_HOURS_START_HOUR: int = 16
    # AFTER_HOURS_END_HOUR already defined above (20)

    # ORB Strategy
    ORB_RANGE_MINUTES: int = 15
    ORB_BREAKOUT_THRESHOLD_PCT: float = 0.1
    ORB_STOP_LOSS_PCT: float = 1.0
    ORB_TAKE_PROFIT_PCT: float = 2.0

    # VWAP Strategy
    VWAP_DEVIATION_THRESHOLD_PCT: float = 1.5
    VWAP_RSI_OVERSOLD: float = 30.0
    VWAP_RSI_OVERBOUGHT: float = 70.0
    VWAP_TARGET_PCT: float = 0.2
    VWAP_STOP_LOSS_PCT: float = 0.8
    VWAP_MAX_HOLD_MINUTES: int = 60

    # Momentum Strategy
    MOMENTUM_VOLUME_RATIO: float = 1.5
    MOMENTUM_RSI_MIN: float = 40.0
    MOMENTUM_RSI_MAX: float = 60.0
    MOMENTUM_TAKE_PROFIT_PCT: float = 1.5
    MOMENTUM_STOP_LOSS_PCT: float = 0.6

    # Gap & Go Strategy
    GAP_MIN_PCT: float = 3.0
    GAP_ENTRY_DELAY_MINUTES: int = 5
    GAP_PULLBACK_PCT: float = 0.5
    GAP_MIN_PREMARKET_VOLUME: int = 200_000
    GAP_STOP_LOSS_PCT: float = 2.0
    GAP_MAX_PROFIT_PCT: float = 5.0
    GAP_EXIT_TIME_HOUR: int = 10
    GAP_EXIT_TIME_MINUTE: int = 30

    # EOD Reversal Strategy
    EOD_START_HOUR: int = 15
    EOD_RSI_OVERSOLD: float = 25.0
    EOD_RSI_OVERBOUGHT: float = 75.0
    EOD_VWAP_DEVIATION_PCT: float = 2.0
    EOD_STOP_LOSS_PCT: float = 1.0
    EOD_TAKE_PROFIT_PCT: float = 1.5
    EOD_EXIT_MINUTE: int = 55  # Exit at 3:55 PM
