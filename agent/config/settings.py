"""Application settings loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with validation."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Alpaca API
    alpaca_api_key: str = Field(..., description="Alpaca API Key ID")
    alpaca_secret_key: str = Field(..., description="Alpaca Secret Key")
    alpaca_base_url: str = Field(
        default="https://paper-api.alpaca.markets",
        description="Alpaca API base URL",
    )
    alpaca_data_feed: Literal["sip", "iex"] = Field(
        default="iex",
        description="Market data feed: 'sip' (real-time, paid $99/mo) or 'iex' (free, ~2%% market)",
    )

    # Trading Configuration
    paper_trading_capital: float = Field(default=100000.0, ge=0)
    environment: Literal["paper", "live"] = Field(default="paper")
    trading_mode: Literal["day_trading", "swing_trading"] = Field(default="day_trading")

    # Risk Management
    max_daily_loss_pct: float = Field(default=2.0, ge=0, le=100)
    max_weekly_loss_pct: float = Field(default=5.0, ge=0, le=100)
    max_monthly_drawdown_pct: float = Field(default=10.0, ge=0, le=100)
    max_position_size_pct: float = Field(default=15.0, ge=0, le=100)
    max_risk_per_trade_pct: float = Field(default=1.0, ge=0, le=100)
    max_concurrent_positions: int = Field(default=10, ge=1)
    max_trades_per_day: int = Field(default=30, ge=1)

    # Trading Hours (Eastern Time)
    market_open_hour: int = Field(default=9, ge=0, le=23)
    market_open_minute: int = Field(default=30, ge=0, le=59)
    market_close_hour: int = Field(default=16, ge=0, le=23)
    market_close_minute: int = Field(default=0, ge=0, le=59)
    avoid_first_minutes: int = Field(default=5, ge=0)
    avoid_last_minutes: int = Field(default=5, ge=0)

    # 24/5 Extended Hours Trading
    # Per Alpaca: Overnight 8PM-4AM, Pre-market 4AM-9:30AM, After-hours 4PM-8PM
    enable_extended_hours: bool = Field(
        default=True,
        description="Enable pre-market and after-hours trading (4AM-8PM ET)",
    )
    enable_overnight_trading: bool = Field(
        default=False,
        description="Enable overnight trading (8PM-4AM ET). Only LIMIT orders with DAY/GTC TIF supported.",
    )

    # Strategy Toggles
    enable_orb: bool = Field(default=True)
    enable_vwap_reversion: bool = Field(default=True)
    enable_momentum_scalp: bool = Field(default=True)
    enable_gap_and_go: bool = Field(default=True)
    enable_eod_reversal: bool = Field(default=True)

    # Machine Learning & Optimization
    enable_ml_learning: bool = Field(default=True)
    enable_auto_disable: bool = Field(default=True)
    enable_ab_testing: bool = Field(default=True)

    # Dynamic Symbol Scanner
    enable_symbol_scanner: bool = Field(
        default=True,
        description="Enable dynamic symbol scanning instead of hardcoded SP500 list",
    )
    scanner_min_price: float = Field(
        default=5.0,
        ge=0,
        description="Minimum stock price for scanner qualification",
    )
    scanner_min_avg_volume: int = Field(
        default=1_000_000,
        ge=0,
        description="Minimum average daily volume for scanner qualification",
    )
    scanner_lookback_days: int = Field(
        default=5,
        ge=1,
        le=30,
        description="Number of days to look back for volume/price screening",
    )
    scanner_max_symbols: int = Field(
        default=1000,
        ge=1,
        description="Maximum number of symbols after scanning. Ignored on IEX (auto-capped to 25).",
    )
    scanner_rescan_interval_minutes: int = Field(
        default=60,
        ge=10,
        description="Minutes between intraday rescans for gap/momentum candidates",
    )

    # Database
    database_url: PostgresDsn = Field(
        ..., description="PostgreSQL connection URL (must be set via DATABASE_URL env var)"
    )

    # Redis (Optional)
    redis_url: RedisDsn | None = Field(default=None)

    # API Configuration
    api_secret_key: str = Field(
        ...,
        description="API secret key for authentication (must be set via API_SECRET_KEY env var)",
    )
    api_host: str = Field(default="0.0.0.0")
    api_port: int = Field(default=8000, ge=1, le=65535)

    # Alerts
    slack_webhook_url: str | None = Field(default=None)
    email_alerts_to: str | None = Field(default=None)
    send_trade_alerts: bool = Field(default=True)
    send_daily_summary: bool = Field(default=True)

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(default="INFO")
    log_format: Literal["json", "text"] = Field(default="json")

    @property
    def is_paper_trading(self) -> bool:
        """Check if running in paper trading mode."""
        return self.environment == "paper"

    @property
    def use_sip_feed(self) -> bool:
        """Check if using SIP (paid real-time) data feed."""
        return self.alpaca_data_feed.lower() == "sip"

    @property
    def use_iex_feed(self) -> bool:
        """Check if using IEX (free, limited) data feed."""
        return not self.use_sip_feed

    # -----------------------------------------------------------------
    # Feed-tier-aware limits
    # All IEX constants are in one place so switching to SIP is a single
    # env-var change (ALPACA_DATA_FEED=sip) with no code edits.
    # -----------------------------------------------------------------

    # IEX hard caps (Alpaca Basic / free plan)
    _IEX_MAX_WEBSOCKET_SYMBOLS: int = 30
    _IEX_MAX_SCANNER_SYMBOLS: int = 25  # leave headroom under 30 WS cap
    _IEX_REST_RATE_LIMIT_PER_MIN: int = 200
    _IEX_SCANNER_BATCH_SIZE: int = 25
    _IEX_SCANNER_BATCH_DELAY: float = 2.0  # seconds between REST batches
    _IEX_RESCAN_INTERVAL_MINUTES: int = 120  # less frequent to save API calls
    _IEX_MAX_SCAN_CANDIDATES: int = 500  # max candidates to screen (saves API calls)

    # SIP practical caps (Algo Trader Plus / $99 mo)
    _SIP_MAX_WEBSOCKET_SYMBOLS: int = 2500
    _SIP_MAX_SCANNER_SYMBOLS: int = 1000
    _SIP_REST_RATE_LIMIT_PER_MIN: int = 10000  # effectively unlimited
    _SIP_SCANNER_BATCH_SIZE: int = 100
    _SIP_SCANNER_BATCH_DELAY: float = 0.5
    _SIP_RESCAN_INTERVAL_MINUTES: int = 60

    @property
    def effective_max_websocket_symbols(self) -> int:
        """Max symbols for WebSocket subscriptions based on feed tier."""
        if self.use_sip_feed:
            return self._SIP_MAX_WEBSOCKET_SYMBOLS
        return self._IEX_MAX_WEBSOCKET_SYMBOLS

    @property
    def effective_scanner_max_symbols(self) -> int:
        """Max symbols the scanner should return based on feed tier."""
        if self.use_sip_feed:
            return min(self.scanner_max_symbols, self._SIP_MAX_SCANNER_SYMBOLS)
        return self._IEX_MAX_SCANNER_SYMBOLS

    @property
    def effective_rest_rate_limit(self) -> int:
        """REST API calls per minute based on feed tier."""
        if self.use_sip_feed:
            return self._SIP_REST_RATE_LIMIT_PER_MIN
        return self._IEX_REST_RATE_LIMIT_PER_MIN

    @property
    def effective_scanner_batch_size(self) -> int:
        """Number of symbols per scanner REST batch based on feed tier."""
        if self.use_sip_feed:
            return self._SIP_SCANNER_BATCH_SIZE
        return self._IEX_SCANNER_BATCH_SIZE

    @property
    def effective_scanner_batch_delay(self) -> float:
        """Delay in seconds between scanner REST batches based on feed tier."""
        if self.use_sip_feed:
            return self._SIP_SCANNER_BATCH_DELAY
        return self._IEX_SCANNER_BATCH_DELAY

    @property
    def effective_scanner_max_candidates(self) -> int | None:
        """Max candidates to screen before applying volume/price filters.

        On IEX (free tier) this caps the number of symbols we fetch bars for,
        drastically reducing startup time and API usage.  Returns None on SIP
        (no cap needed — rate limits are effectively unlimited).
        """
        if self.use_sip_feed:
            return None
        return self._IEX_MAX_SCAN_CANDIDATES

    @property
    def effective_rescan_interval_minutes(self) -> int:
        """Minutes between intraday rescans based on feed tier."""
        if self.use_sip_feed:
            return self.scanner_rescan_interval_minutes
        return self._IEX_RESCAN_INTERVAL_MINUTES

    @property
    def max_daily_loss_amount(self) -> float:
        """Calculate max daily loss in dollars."""
        return self.paper_trading_capital * (self.max_daily_loss_pct / 100)

    @property
    def max_position_size_amount(self) -> float:
        """Calculate max position size in dollars."""
        return self.paper_trading_capital * (self.max_position_size_pct / 100)

    @property
    def max_risk_per_trade_amount(self) -> float:
        """Calculate max risk per trade in dollars."""
        return self.paper_trading_capital * (self.max_risk_per_trade_pct / 100)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
