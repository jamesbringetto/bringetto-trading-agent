"""Initial schema with all trading agent tables.

Revision ID: 0001
Revises:
Create Date: 2026-02-03

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create enum types
    op.execute(
        "CREATE TYPE strategytype AS ENUM ('orb', 'vwap_reversion', 'momentum_scalp', 'gap_and_go', 'eod_reversal', 'experimental')"
    )
    op.execute("CREATE TYPE orderside AS ENUM ('buy', 'sell')")
    op.execute("CREATE TYPE tradestatus AS ENUM ('open', 'closed', 'cancelled', 'partial')")
    op.execute("CREATE TYPE decisiontype AS ENUM ('entry', 'exit', 'hold', 'skip')")
    op.execute(
        "CREATE TYPE marketregime AS ENUM ('trending_up', 'trending_down', 'range_bound', 'high_volatility', 'low_volatility', 'unknown')"
    )
    op.execute("CREATE TYPE alertseverity AS ENUM ('info', 'warning', 'error', 'critical')")

    # strategies table
    op.create_table(
        "strategies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        sa.Column("version", sa.String(20), nullable=False, server_default="1.0.0"),
        sa.Column(
            "type",
            postgresql.ENUM(
                "orb",
                "vwap_reversion",
                "momentum_scalp",
                "gap_and_go",
                "eod_reversal",
                "experimental",
                name="strategytype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("parameters", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("is_experimental", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("disabled_reason", sa.Text, nullable=True),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    # trades table
    op.create_table(
        "trades",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("symbol", sa.String(10), nullable=False, index=True),
        sa.Column(
            "strategy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("strategies.id"),
            nullable=False,
        ),
        sa.Column(
            "side",
            postgresql.ENUM("buy", "sell", name="orderside", create_type=False),
            nullable=False,
        ),
        sa.Column("entry_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("exit_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("quantity", sa.Numeric(10, 4), nullable=False),
        sa.Column("pnl", sa.Numeric(10, 2), nullable=True),
        sa.Column("pnl_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("commission", sa.Numeric(10, 2), server_default="0"),
        sa.Column(
            "status",
            postgresql.ENUM(
                "open", "closed", "cancelled", "partial", name="tradestatus", create_type=False
            ),
            nullable=False,
            server_default="open",
        ),
        sa.Column("entry_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("exit_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("holding_time_seconds", sa.Integer, nullable=True),
        sa.Column("stop_loss", sa.Numeric(10, 2), nullable=False),
        sa.Column("take_profit", sa.Numeric(10, 2), nullable=False),
        sa.Column("broker_order_id", sa.String(100), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("quantity > 0", name="check_positive_quantity"),
        sa.CheckConstraint("entry_price > 0", name="check_positive_entry_price"),
    )
    op.create_index("ix_trades_timestamp", "trades", ["timestamp"])
    op.create_index("ix_trades_strategy_status", "trades", ["strategy_id", "status"])

    # trade_decisions table
    op.create_table(
        "trade_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "trade_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("trades.id"), nullable=True
        ),
        sa.Column(
            "timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "decision_type",
            postgresql.ENUM(
                "entry", "exit", "hold", "skip", name="decisiontype", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("strategy_name", sa.String(50), nullable=False),
        sa.Column("strategy_version", sa.String(20), nullable=False),
        sa.Column("symbol", sa.String(10), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("vix", sa.Numeric(5, 2), nullable=True),
        sa.Column("volume", sa.Integer, nullable=True),
        sa.Column("trend", sa.String(10), nullable=True),
        sa.Column("indicators", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("expected_profit_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("expected_loss_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("actual_profit_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("reasoning_text", sa.Text, nullable=False),
        sa.Column("confidence_score", sa.Numeric(3, 2), nullable=True),
        sa.Column("outcome", sa.String(10), nullable=True),
        sa.Column("what_worked", sa.Text, nullable=True),
        sa.Column("what_failed", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="check_confidence_range",
        ),
    )
    op.create_index("ix_trade_decisions_timestamp", "trade_decisions", ["timestamp"])
    op.create_index("ix_trade_decisions_strategy", "trade_decisions", ["strategy_name"])

    # strategy_performance table
    op.create_table(
        "strategy_performance",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "strategy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("strategies.id"),
            nullable=False,
        ),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trades_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("wins", sa.Integer, nullable=False, server_default="0"),
        sa.Column("losses", sa.Integer, nullable=False, server_default="0"),
        sa.Column("win_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("total_pnl", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("total_pnl_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("gross_profit", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("gross_loss", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("profit_factor", sa.Numeric(5, 2), nullable=True),
        sa.Column("sharpe_ratio", sa.Numeric(5, 2), nullable=True),
        sa.Column("max_drawdown", sa.Numeric(10, 2), nullable=True),
        sa.Column("avg_win", sa.Numeric(10, 2), nullable=True),
        sa.Column("avg_loss", sa.Numeric(10, 2), nullable=True),
        sa.Column("avg_hold_time_seconds", sa.Integer, nullable=True),
        sa.Column("largest_win", sa.Numeric(10, 2), nullable=True),
        sa.Column("largest_loss", sa.Numeric(10, 2), nullable=True),
        sa.Column("consecutive_losses", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("strategy_id", "date", name="uq_strategy_date"),
    )
    op.create_index("ix_strategy_performance_date", "strategy_performance", ["date"])

    # ab_tests table
    op.create_table(
        "ab_tests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column(
            "variant_a_strategy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("strategies.id"),
            nullable=False,
        ),
        sa.Column(
            "variant_b_strategy_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("strategies.id"),
            nullable=False,
        ),
        sa.Column("variant_a_trades", sa.Integer, nullable=False, server_default="0"),
        sa.Column("variant_b_trades", sa.Integer, nullable=False, server_default="0"),
        sa.Column("variant_a_win_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("variant_b_win_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("variant_a_profit_factor", sa.Numeric(5, 2), nullable=True),
        sa.Column("variant_b_profit_factor", sa.Numeric(5, 2), nullable=True),
        sa.Column("winner", sa.String(20), nullable=True),
        sa.Column("p_value", sa.Numeric(5, 4), nullable=True),
        sa.Column("statistical_significance", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('active', 'completed', 'cancelled')", name="check_ab_status"
        ),
    )

    # market_regimes table
    op.create_table(
        "market_regimes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("symbol", sa.String(10), nullable=False),
        sa.Column(
            "regime_type",
            postgresql.ENUM(
                "trending_up",
                "trending_down",
                "range_bound",
                "high_volatility",
                "low_volatility",
                "unknown",
                name="marketregime",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("adx", sa.Numeric(5, 2), nullable=True),
        sa.Column("vix", sa.Numeric(5, 2), nullable=True),
        sa.Column("volume_ratio", sa.Numeric(5, 2), nullable=True),
        sa.Column("trend_strength", sa.Numeric(5, 2), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_market_regimes_symbol", "market_regimes", ["symbol"])
    op.create_index("ix_market_regimes_timestamp_symbol", "market_regimes", ["timestamp", "symbol"])

    # daily_summaries table
    op.create_table(
        "daily_summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False, unique=True),
        sa.Column("total_trades", sa.Integer, nullable=False, server_default="0"),
        sa.Column("winning_trades", sa.Integer, nullable=False, server_default="0"),
        sa.Column("losing_trades", sa.Integer, nullable=False, server_default="0"),
        sa.Column("win_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("total_pnl", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("total_pnl_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("best_trade", sa.Numeric(10, 2), nullable=True),
        sa.Column("worst_trade", sa.Numeric(10, 2), nullable=True),
        sa.Column("sharpe_ratio", sa.Numeric(5, 2), nullable=True),
        sa.Column("profit_factor", sa.Numeric(5, 2), nullable=True),
        sa.Column("max_drawdown", sa.Numeric(10, 2), nullable=True),
        sa.Column("strategies_active", sa.Integer, nullable=False, server_default="0"),
        sa.Column("account_balance", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_daily_summaries_date", "daily_summaries", ["date"])

    # alerts table
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "severity",
            postgresql.ENUM(
                "info", "warning", "error", "critical", name="alertseverity", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("is_read", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_resolved", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_alerts_timestamp_severity", "alerts", ["timestamp", "severity"])

    # system_health table
    op.create_table(
        "system_health",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("cpu_usage", sa.Numeric(5, 2), nullable=True),
        sa.Column("memory_usage", sa.Numeric(5, 2), nullable=True),
        sa.Column("active_websockets", sa.Integer, nullable=False, server_default="0"),
        sa.Column("active_strategies", sa.Integer, nullable=False, server_default="0"),
        sa.Column("open_positions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_trade", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_system_health_timestamp", "system_health", ["timestamp"])


def downgrade() -> None:
    op.drop_table("system_health")
    op.drop_table("alerts")
    op.drop_table("daily_summaries")
    op.drop_table("market_regimes")
    op.drop_table("ab_tests")
    op.drop_table("strategy_performance")
    op.drop_table("trade_decisions")
    op.drop_table("trades")
    op.drop_table("strategies")

    op.execute("DROP TYPE IF EXISTS alertseverity")
    op.execute("DROP TYPE IF EXISTS marketregime")
    op.execute("DROP TYPE IF EXISTS decisiontype")
    op.execute("DROP TYPE IF EXISTS tradestatus")
    op.execute("DROP TYPE IF EXISTS orderside")
    op.execute("DROP TYPE IF EXISTS strategytype")
