"""Add instrumentation_snapshots table for persisting counter data.

Revision ID: 0003
Revises: 0002
Create Date: 2026-02-06

Stores periodic delta snapshots of instrumentation counters so that
dashboard metrics survive agent redeployments and support historical
time-range queries (last 1d, 7d, 30d, etc.).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "instrumentation_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        # Data reception deltas
        sa.Column("bars_received", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quotes_received", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trades_received", sa.Integer(), nullable=False, server_default="0"),
        # Evaluation count deltas
        sa.Column("total_evaluations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accepted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped", sa.Integer(), nullable=False, server_default="0"),
        # Funnel stage deltas
        sa.Column(
            "funnel",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
        # Risk rejection breakdown deltas
        sa.Column(
            "risk_rejection_breakdown",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
        # Per-strategy data deltas
        sa.Column(
            "by_strategy",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
    )

    op.create_index(
        "ix_instrumentation_snapshots_timestamp",
        "instrumentation_snapshots",
        ["timestamp"],
    )
    op.create_index(
        "ix_instrumentation_snapshots_period",
        "instrumentation_snapshots",
        ["period_start", "period_end"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_instrumentation_snapshots_period",
        table_name="instrumentation_snapshots",
    )
    op.drop_index(
        "ix_instrumentation_snapshots_timestamp",
        table_name="instrumentation_snapshots",
    )
    op.drop_table("instrumentation_snapshots")
