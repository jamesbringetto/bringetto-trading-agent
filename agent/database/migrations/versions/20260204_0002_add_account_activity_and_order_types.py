"""Add account activities, account snapshots, and order type/class to trades.

Revision ID: 0002
Revises: 0001
Create Date: 2026-02-04

Per Alpaca API documentation:
- AccountActivity tracks non-trade activities (dividends, fees, transfers, etc.)
- AccountSnapshot captures daily account state for historical tracking
- Order type and class fields on trades for better order tracking
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create new enum types
    op.execute("""
        CREATE TYPE accountactivitytype AS ENUM (
            'FILL', 'TRANS', 'MISC', 'ACATC', 'ACATS', 'CSD', 'CSR',
            'DIV', 'DIVCGL', 'DIVCGS', 'DIVFEE', 'DIVFT', 'DIVNRA',
            'DIVROC', 'DIVTW', 'DIVTXEX', 'INT', 'INTNRA', 'INTTW',
            'JNL', 'JNLC', 'JNLS', 'MA', 'NC', 'OPASN', 'OPEXP',
            'OPXRC', 'PTC', 'PTR', 'REORG', 'SC', 'SSO', 'SSP',
            'FEE', 'CFEE'
        )
    """)
    op.execute(
        "CREATE TYPE ordertype AS ENUM ('market', 'limit', 'stop', 'stop_limit', 'trailing_stop')"
    )
    op.execute("CREATE TYPE orderclass AS ENUM ('simple', 'bracket', 'oco', 'oto')")

    # Add order_type and order_class columns to trades table
    op.add_column(
        "trades",
        sa.Column(
            "order_type",
            postgresql.ENUM(
                "market",
                "limit",
                "stop",
                "stop_limit",
                "trailing_stop",
                name="ordertype",
                create_type=False,
            ),
            nullable=False,
            server_default="market",
        ),
    )
    op.add_column(
        "trades",
        sa.Column(
            "order_class",
            postgresql.ENUM(
                "simple", "bracket", "oco", "oto", name="orderclass", create_type=False
            ),
            nullable=False,
            server_default="simple",
        ),
    )

    # Create account_activities table
    op.create_table(
        "account_activities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("activity_id", sa.String(100), nullable=False, unique=True),
        sa.Column(
            "activity_type",
            postgresql.ENUM(
                "FILL",
                "TRANS",
                "MISC",
                "ACATC",
                "ACATS",
                "CSD",
                "CSR",
                "DIV",
                "DIVCGL",
                "DIVCGS",
                "DIVFEE",
                "DIVFT",
                "DIVNRA",
                "DIVROC",
                "DIVTW",
                "DIVTXEX",
                "INT",
                "INTNRA",
                "INTTW",
                "JNL",
                "JNLC",
                "JNLS",
                "MA",
                "NC",
                "OPASN",
                "OPEXP",
                "OPXRC",
                "PTC",
                "PTR",
                "REORG",
                "SC",
                "SSO",
                "SSP",
                "FEE",
                "CFEE",
                name="accountactivitytype",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("net_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("symbol", sa.String(10), nullable=True),
        sa.Column("qty", sa.Numeric(12, 4), nullable=True),
        sa.Column("per_share_amount", sa.Numeric(10, 4), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("leaves_qty", sa.Numeric(12, 4), nullable=True),
        sa.Column("price", sa.Numeric(10, 2), nullable=True),
        sa.Column("cum_qty", sa.Numeric(12, 4), nullable=True),
        sa.Column("side", sa.String(10), nullable=True),
        sa.Column("order_id", sa.String(100), nullable=True),
        sa.Column("transaction_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_account_activities_date", "account_activities", ["date"])
    op.create_index("ix_account_activities_type", "account_activities", ["activity_type"])
    op.create_index("ix_account_activities_symbol", "account_activities", ["symbol"])

    # Create account_snapshots table
    op.create_table(
        "account_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False, unique=True),
        # Core account values
        sa.Column("cash", sa.Numeric(12, 2), nullable=False),
        sa.Column("portfolio_value", sa.Numeric(12, 2), nullable=False),
        sa.Column("equity", sa.Numeric(12, 2), nullable=False),
        sa.Column("last_equity", sa.Numeric(12, 2), nullable=True),
        # Buying power metrics
        sa.Column("buying_power", sa.Numeric(12, 2), nullable=False),
        sa.Column("regt_buying_power", sa.Numeric(12, 2), nullable=True),
        sa.Column("daytrading_buying_power", sa.Numeric(12, 2), nullable=True),
        sa.Column("non_marginable_buying_power", sa.Numeric(12, 2), nullable=True),
        # Position values
        sa.Column("long_market_value", sa.Numeric(12, 2), nullable=True),
        sa.Column("short_market_value", sa.Numeric(12, 2), nullable=True),
        sa.Column("position_market_value", sa.Numeric(12, 2), nullable=True),
        # Margin-related
        sa.Column("initial_margin", sa.Numeric(12, 2), nullable=True),
        sa.Column("maintenance_margin", sa.Numeric(12, 2), nullable=True),
        sa.Column("sma", sa.Numeric(12, 2), nullable=True),
        sa.Column("leverage", sa.Numeric(5, 2), nullable=True),
        # Day trading
        sa.Column("daytrade_count", sa.Integer, nullable=True),
        sa.Column("pattern_day_trader", sa.Boolean, nullable=True),
        # P&L
        sa.Column("pending_transfer_in", sa.Numeric(12, 2), nullable=True),
        sa.Column("pending_transfer_out", sa.Numeric(12, 2), nullable=True),
        sa.Column("accrued_fees", sa.Numeric(12, 2), nullable=True),
        # Tracking fields
        sa.Column("open_positions_count", sa.Integer, nullable=True),
        sa.Column("daily_pnl", sa.Numeric(12, 2), nullable=True),
        sa.Column("daily_pnl_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_account_snapshots_date", "account_snapshots", ["date"])


def downgrade() -> None:
    # Drop tables
    op.drop_table("account_snapshots")
    op.drop_table("account_activities")

    # Drop columns from trades
    op.drop_column("trades", "order_class")
    op.drop_column("trades", "order_type")

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS orderclass")
    op.execute("DROP TYPE IF EXISTS ordertype")
    op.execute("DROP TYPE IF EXISTS accountactivitytype")
