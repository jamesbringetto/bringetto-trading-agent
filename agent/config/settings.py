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
        default="sip",
        description="Market data feed: 'sip' (real-time, paid) or 'iex' (free, limited)",
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

    # Database
    database_url: PostgresDsn = Field(
        default="postgresql://postgres:postgres@localhost:5432/trading_agent"
    )

    # Redis (Optional)
    redis_url: RedisDsn | None = Field(default=None)

    # API Configuration
    api_secret_key: str = Field(default="change_this_to_a_random_secret_key")
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
