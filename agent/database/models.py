"""SQLAlchemy database models for the trading agent."""

import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func

from agent.config.constants import (
    AccountActivityType,
    AlertSeverity,
    DecisionType,
    MarketRegime,
    OrderClass,
    OrderSide,
    OrderType,
    StrategyType,
    TradeStatus,
)


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class Strategy(Base):
    """Trading strategy configurations."""

    __tablename__ = "strategies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(50), nullable=False, unique=True)
    version = Column(String(20), nullable=False, default="1.0.0")
    type = Column(
        Enum(StrategyType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    parameters = Column(JSONB, nullable=False, default=dict)
    is_active = Column(Boolean, default=True, nullable=False)
    is_experimental = Column(Boolean, default=False, nullable=False)
    disabled_reason = Column(Text, nullable=True)
    disabled_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    trades = relationship("Trade", back_populates="strategy")
    performance_records = relationship("StrategyPerformance", back_populates="strategy")

    def __repr__(self) -> str:
        return f"<Strategy(name={self.name}, type={self.type}, active={self.is_active})>"


class Trade(Base):
    """Executed trades."""

    __tablename__ = "trades"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=func.now())
    symbol = Column(String(10), nullable=False, index=True)
    strategy_id = Column(UUID(as_uuid=True), ForeignKey("strategies.id"), nullable=False)
    side = Column(
        Enum(OrderSide, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    order_type = Column(
        Enum(OrderType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=OrderType.MARKET,
    )
    order_class = Column(
        Enum(OrderClass, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=OrderClass.SIMPLE,
    )
    entry_price = Column(Numeric(10, 2), nullable=False)
    exit_price = Column(Numeric(10, 2), nullable=True)
    quantity = Column(Numeric(10, 4), nullable=False)
    pnl = Column(Numeric(10, 2), nullable=True)
    pnl_percent = Column(Numeric(5, 2), nullable=True)
    commission = Column(Numeric(10, 2), default=0)
    status = Column(
        Enum(TradeStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=TradeStatus.OPEN,
    )
    entry_time = Column(DateTime(timezone=True), nullable=False)
    exit_time = Column(DateTime(timezone=True), nullable=True)
    holding_time_seconds = Column(Integer, nullable=True)
    stop_loss = Column(Numeric(10, 2), nullable=False)
    take_profit = Column(Numeric(10, 2), nullable=False)
    broker_order_id = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    strategy = relationship("Strategy", back_populates="trades")
    decisions = relationship("TradeDecision", back_populates="trade")

    __table_args__ = (
        Index("ix_trades_timestamp", "timestamp"),
        Index("ix_trades_strategy_status", "strategy_id", "status"),
        CheckConstraint("quantity > 0", name="check_positive_quantity"),
        CheckConstraint("entry_price > 0", name="check_positive_entry_price"),
    )

    def __repr__(self) -> str:
        return f"<Trade(symbol={self.symbol}, side={self.side}, status={self.status})>"


class TradeDecision(Base):
    """Complete reasoning for every trade decision."""

    __tablename__ = "trade_decisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trade_id = Column(UUID(as_uuid=True), ForeignKey("trades.id"), nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=func.now())
    decision_type = Column(
        Enum(DecisionType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    strategy_name = Column(String(50), nullable=False)
    strategy_version = Column(String(20), nullable=False)

    # Market context at decision time
    symbol = Column(String(10), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    vix = Column(Numeric(5, 2), nullable=True)
    volume = Column(Integer, nullable=True)
    trend = Column(String(10), nullable=True)

    # Indicators that triggered decision
    indicators = Column(JSONB, nullable=False, default=dict)

    # Expected vs actual
    expected_profit_pct = Column(Numeric(5, 2), nullable=True)
    expected_loss_pct = Column(Numeric(5, 2), nullable=True)
    actual_profit_pct = Column(Numeric(5, 2), nullable=True)

    # Reasoning
    reasoning_text = Column(Text, nullable=False)
    confidence_score = Column(Numeric(3, 2), nullable=True)

    # Outcome analysis
    outcome = Column(String(10), nullable=True)  # win, loss, breakeven
    what_worked = Column(Text, nullable=True)
    what_failed = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    trade = relationship("Trade", back_populates="decisions")

    __table_args__ = (
        Index("ix_trade_decisions_timestamp", "timestamp"),
        Index("ix_trade_decisions_strategy", "strategy_name"),
        CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="check_confidence_range",
        ),
    )

    def __repr__(self) -> str:
        return f"<TradeDecision(type={self.decision_type}, strategy={self.strategy_name})>"


class StrategyPerformance(Base):
    """Real-time performance per strategy per day."""

    __tablename__ = "strategy_performance"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    strategy_id = Column(UUID(as_uuid=True), ForeignKey("strategies.id"), nullable=False)
    date = Column(DateTime(timezone=True), nullable=False)
    trades_count = Column(Integer, default=0, nullable=False)
    wins = Column(Integer, default=0, nullable=False)
    losses = Column(Integer, default=0, nullable=False)
    win_rate = Column(Numeric(5, 2), nullable=True)
    total_pnl = Column(Numeric(10, 2), default=0, nullable=False)
    total_pnl_pct = Column(Numeric(5, 2), nullable=True)
    gross_profit = Column(Numeric(10, 2), default=0, nullable=False)
    gross_loss = Column(Numeric(10, 2), default=0, nullable=False)
    profit_factor = Column(Numeric(5, 2), nullable=True)
    sharpe_ratio = Column(Numeric(5, 2), nullable=True)
    max_drawdown = Column(Numeric(10, 2), nullable=True)
    avg_win = Column(Numeric(10, 2), nullable=True)
    avg_loss = Column(Numeric(10, 2), nullable=True)
    avg_hold_time_seconds = Column(Integer, nullable=True)
    largest_win = Column(Numeric(10, 2), nullable=True)
    largest_loss = Column(Numeric(10, 2), nullable=True)
    consecutive_losses = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    strategy = relationship("Strategy", back_populates="performance_records")

    __table_args__ = (
        UniqueConstraint("strategy_id", "date", name="uq_strategy_date"),
        Index("ix_strategy_performance_date", "date"),
    )

    def __repr__(self) -> str:
        return f"<StrategyPerformance(strategy_id={self.strategy_id}, date={self.date})>"


class ABTest(Base):
    """A/B testing experiments."""

    __tablename__ = "ab_tests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    start_date = Column(DateTime(timezone=True), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), default="active", nullable=False)
    variant_a_strategy_id = Column(UUID(as_uuid=True), ForeignKey("strategies.id"), nullable=False)
    variant_b_strategy_id = Column(UUID(as_uuid=True), ForeignKey("strategies.id"), nullable=False)
    variant_a_trades = Column(Integer, default=0, nullable=False)
    variant_b_trades = Column(Integer, default=0, nullable=False)
    variant_a_win_rate = Column(Numeric(5, 2), nullable=True)
    variant_b_win_rate = Column(Numeric(5, 2), nullable=True)
    variant_a_profit_factor = Column(Numeric(5, 2), nullable=True)
    variant_b_profit_factor = Column(Numeric(5, 2), nullable=True)
    winner = Column(String(20), nullable=True)  # 'a', 'b', 'inconclusive'
    p_value = Column(Numeric(5, 4), nullable=True)
    statistical_significance = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('active', 'completed', 'cancelled')", name="check_ab_status"),
    )

    def __repr__(self) -> str:
        return f"<ABTest(name={self.name}, status={self.status})>"


class MarketRegimeRecord(Base):
    """Detected market conditions."""

    __tablename__ = "market_regimes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=func.now())
    symbol = Column(String(10), nullable=False, index=True)
    regime_type = Column(
        Enum(MarketRegime, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    adx = Column(Numeric(5, 2), nullable=True)
    vix = Column(Numeric(5, 2), nullable=True)
    volume_ratio = Column(Numeric(5, 2), nullable=True)
    trend_strength = Column(Numeric(5, 2), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_market_regimes_timestamp_symbol", "timestamp", "symbol"),)

    def __repr__(self) -> str:
        return f"<MarketRegimeRecord(symbol={self.symbol}, regime={self.regime_type})>"


class DailySummary(Base):
    """Daily performance rollups."""

    __tablename__ = "daily_summaries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    date = Column(DateTime(timezone=True), nullable=False, unique=True)
    total_trades = Column(Integer, default=0, nullable=False)
    winning_trades = Column(Integer, default=0, nullable=False)
    losing_trades = Column(Integer, default=0, nullable=False)
    win_rate = Column(Numeric(5, 2), nullable=True)
    total_pnl = Column(Numeric(10, 2), default=0, nullable=False)
    total_pnl_pct = Column(Numeric(5, 2), nullable=True)
    best_trade = Column(Numeric(10, 2), nullable=True)
    worst_trade = Column(Numeric(10, 2), nullable=True)
    sharpe_ratio = Column(Numeric(5, 2), nullable=True)
    profit_factor = Column(Numeric(5, 2), nullable=True)
    max_drawdown = Column(Numeric(10, 2), nullable=True)
    strategies_active = Column(Integer, default=0, nullable=False)
    account_balance = Column(Numeric(12, 2), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_daily_summaries_date", "date"),)

    def __repr__(self) -> str:
        return f"<DailySummary(date={self.date}, pnl={self.total_pnl})>"


class Alert(Base):
    """System alerts."""

    __tablename__ = "alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=func.now())
    severity = Column(
        Enum(AlertSeverity, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    type = Column(String(50), nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False, nullable=False)
    is_resolved = Column(Boolean, default=False, nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_alerts_timestamp_severity", "timestamp", "severity"),)

    def __repr__(self) -> str:
        return f"<Alert(severity={self.severity}, type={self.type})>"


class SystemHealth(Base):
    """Agent health metrics."""

    __tablename__ = "system_health"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=func.now())
    cpu_usage = Column(Numeric(5, 2), nullable=True)
    memory_usage = Column(Numeric(5, 2), nullable=True)
    active_websockets = Column(Integer, default=0, nullable=False)
    active_strategies = Column(Integer, default=0, nullable=False)
    open_positions = Column(Integer, default=0, nullable=False)
    last_heartbeat = Column(DateTime(timezone=True), nullable=True)
    last_trade = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_system_health_timestamp", "timestamp"),)

    def __repr__(self) -> str:
        return f"<SystemHealth(timestamp={self.timestamp})>"


class AccountActivity(Base):
    """Non-trade account activities per Alpaca Activities API.

    Tracks dividends, interest, fees, transfers, corporate actions, etc.
    This is separate from trades to capture all account-affecting events.
    """

    __tablename__ = "account_activities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    activity_id = Column(String(100), nullable=False, unique=True)  # Alpaca activity ID
    activity_type = Column(
        Enum(AccountActivityType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    date = Column(DateTime(timezone=True), nullable=False)
    net_amount = Column(Numeric(12, 2), nullable=True)  # Cash amount (can be negative)
    symbol = Column(String(10), nullable=True)  # Symbol if applicable
    qty = Column(Numeric(12, 4), nullable=True)  # Quantity if applicable
    per_share_amount = Column(Numeric(10, 4), nullable=True)  # Per-share amount for DIV, etc.
    description = Column(Text, nullable=True)  # Activity description
    status = Column(String(20), nullable=True)  # executed, pending, cancelled
    leaves_qty = Column(Numeric(12, 4), nullable=True)  # Remaining quantity
    price = Column(Numeric(10, 2), nullable=True)  # Price per share if applicable
    cum_qty = Column(Numeric(12, 4), nullable=True)  # Cumulative quantity
    side = Column(String(10), nullable=True)  # buy, sell for FILL activities
    order_id = Column(String(100), nullable=True)  # Associated order ID for fills
    transaction_time = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_account_activities_date", "date"),
        Index("ix_account_activities_type", "activity_type"),
        Index("ix_account_activities_symbol", "symbol"),
    )

    def __repr__(self) -> str:
        return f"<AccountActivity(type={self.activity_type}, amount={self.net_amount})>"


class AccountSnapshot(Base):
    """Daily snapshot of account state per Alpaca Account API.

    Captures daily account values for tracking equity curves, margin usage,
    buying power changes, and historical account state.
    """

    __tablename__ = "account_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    date = Column(DateTime(timezone=True), nullable=False, unique=True)

    # Core account values
    cash = Column(Numeric(12, 2), nullable=False)
    portfolio_value = Column(Numeric(12, 2), nullable=False)
    equity = Column(Numeric(12, 2), nullable=False)
    last_equity = Column(Numeric(12, 2), nullable=True)  # Previous day's equity

    # Buying power metrics
    buying_power = Column(Numeric(12, 2), nullable=False)
    regt_buying_power = Column(Numeric(12, 2), nullable=True)  # Reg T buying power
    daytrading_buying_power = Column(Numeric(12, 2), nullable=True)  # 4x for PDT
    non_marginable_buying_power = Column(Numeric(12, 2), nullable=True)

    # Position values
    long_market_value = Column(Numeric(12, 2), nullable=True)
    short_market_value = Column(Numeric(12, 2), nullable=True)
    position_market_value = Column(Numeric(12, 2), nullable=True)

    # Margin-related
    initial_margin = Column(Numeric(12, 2), nullable=True)
    maintenance_margin = Column(Numeric(12, 2), nullable=True)
    sma = Column(Numeric(12, 2), nullable=True)  # Special memorandum account
    leverage = Column(Numeric(5, 2), nullable=True)  # Current leverage ratio

    # Day trading
    daytrade_count = Column(Integer, nullable=True)  # Number of day trades
    pattern_day_trader = Column(Boolean, nullable=True)

    # P&L
    pending_transfer_in = Column(Numeric(12, 2), nullable=True)
    pending_transfer_out = Column(Numeric(12, 2), nullable=True)
    accrued_fees = Column(Numeric(12, 2), nullable=True)

    # Tracking fields
    open_positions_count = Column(Integer, nullable=True)
    daily_pnl = Column(Numeric(12, 2), nullable=True)  # Calculated from last_equity
    daily_pnl_pct = Column(Numeric(5, 2), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (Index("ix_account_snapshots_date", "date"),)

    def __repr__(self) -> str:
        return f"<AccountSnapshot(date={self.date}, equity={self.equity})>"
