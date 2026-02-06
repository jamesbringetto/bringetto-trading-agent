"""Instrumentation API endpoints for observability."""

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from loguru import logger

from agent.api.auth import require_api_key
from agent.monitoring.instrumentation import get_instrumentation

# All endpoints in this router require API key authentication
router = APIRouter(dependencies=[Depends(require_api_key)])

# Valid time range values and their corresponding timedelta
TIME_RANGE_MAP: dict[str, timedelta | None] = {
    "session": None,  # Current session only (in-memory)
    "1d": timedelta(days=1),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


def _resolve_time_range(time_range: str) -> datetime | None:
    """Convert a time_range string to a UTC cutoff datetime.

    Returns None for 'session' (use in-memory data only).
    """
    td = TIME_RANGE_MAP.get(time_range)
    if td is None:
        return None
    return datetime.utcnow() - td


@router.get("/")
async def get_instrumentation_status(
    time_range: str = Query(
        "session",
        description="Time range for counters: session, 1d, 7d, 30d",
        pattern="^(session|1d|7d|30d)$",
    ),
) -> dict[str, Any]:
    """
    Get complete instrumentation status.

    Returns data reception stats, evaluation summary, and recent accepted signals.

    The `time_range` parameter controls the scope of counters:
    - `session`: Current agent session only (in-memory, default)
    - `1d`: Last 24 hours (persisted across redeployments)
    - `7d`: Last 7 days
    - `30d`: Last 30 days
    """
    try:
        inst = get_instrumentation()
        since = _resolve_time_range(time_range)

        if since is None:
            # Session mode: use in-memory data (original behavior)
            return inst.get_status()

        # Historical mode: query DB + current unsaved delta
        historical = inst.get_historical_summary(since)

        return {
            "data_reception": {
                **inst.get_data_stats(),
                # Override totals with historical values
                "total_bars": historical["bars_received"],
                "total_quotes": historical["quotes_received"],
                "total_trades": historical["trades_received"],
            },
            "evaluations": {
                "time_window_minutes": int(TIME_RANGE_MAP[time_range].total_seconds() / 60),
                "total_evaluations": historical["total_evaluations"],
                "accepted": historical["accepted"],
                "rejected": historical["rejected"],
                "skipped": historical["skipped"],
                "acceptance_rate": historical["acceptance_rate"],
                "by_strategy": historical["by_strategy"],
                "by_symbol": {},  # Not tracked in snapshots
                "funnel": historical["funnel"],
                "risk_rejection_breakdown": historical["risk_rejection_breakdown"],
            },
            "recent_accepted_signals": inst.get_evaluations(decision="accepted", limit=10),
        }
    except Exception as e:
        logger.error(f"Failed to get instrumentation status: {e}")
        return {
            "error": str(e),
            "data_reception": None,
            "evaluations": None,
            "recent_accepted_signals": [],
        }


@router.get("/data-reception")
async def get_data_reception_stats(
    time_range: str = Query(
        "session",
        description="Time range: session, 1d, 7d, 30d",
        pattern="^(session|1d|7d|30d)$",
    ),
) -> dict[str, Any]:
    """
    Get market data reception statistics.

    Shows:
    - Total bars, quotes, trades received
    - Data reception rates (per second)
    - Data freshness (time since last data)
    - Symbol counts
    """
    try:
        inst = get_instrumentation()
        stats = inst.get_data_stats()
        since = _resolve_time_range(time_range)

        if since is not None:
            historical = inst.get_historical_summary(since)
            stats["total_bars"] = historical["bars_received"]
            stats["total_quotes"] = historical["quotes_received"]
            stats["total_trades"] = historical["trades_received"]

        return stats
    except Exception as e:
        logger.error(f"Failed to get data reception stats: {e}")
        return {"error": str(e)}


@router.get("/evaluations")
async def get_evaluations(
    strategy_name: str | None = Query(None, description="Filter by strategy name"),
    symbol: str | None = Query(None, description="Filter by symbol"),
    decision: str | None = Query(
        None, description="Filter by decision (accepted, rejected, skipped)"
    ),
    minutes: int = Query(60, description="Time window in minutes"),
    limit: int = Query(100, description="Maximum number of results"),
) -> list[dict[str, Any]]:
    """
    Get recent strategy evaluations.

    Returns detailed information about each evaluation including:
    - Market context at evaluation time
    - Decision (accepted/rejected/skipped)
    - Rejection reason (if rejected)
    - Signal details (if accepted)
    """
    try:
        inst = get_instrumentation()
        since = datetime.utcnow() - timedelta(minutes=minutes)
        return inst.get_evaluations(
            strategy_name=strategy_name,
            symbol=symbol,
            decision=decision,
            since=since,
            limit=limit,
        )
    except Exception as e:
        logger.error(f"Failed to get evaluations: {e}")
        return []


@router.get("/evaluations/summary")
async def get_evaluation_summary(
    minutes: int = Query(60, description="Time window in minutes"),
    time_range: str = Query(
        "session",
        description="Time range: session, 1d, 7d, 30d",
        pattern="^(session|1d|7d|30d)$",
    ),
) -> dict[str, Any]:
    """
    Get evaluation summary statistics.

    Shows:
    - Total evaluations
    - Accepted/rejected counts
    - Acceptance rate
    - Breakdown by strategy
    - Top symbols evaluated
    """
    try:
        inst = get_instrumentation()
        since = _resolve_time_range(time_range)

        if since is not None:
            historical = inst.get_historical_summary(since)
            historical["time_window_minutes"] = int(TIME_RANGE_MAP[time_range].total_seconds() / 60)
            historical["by_symbol"] = {}
            return historical

        return inst.get_evaluation_summary(minutes=minutes)
    except Exception as e:
        logger.error(f"Failed to get evaluation summary: {e}")
        return {"error": str(e)}


@router.post("/heartbeat")
async def trigger_heartbeat() -> dict[str, str]:
    """Manually trigger a heartbeat log."""
    try:
        inst = get_instrumentation()
        inst.log_heartbeat()
        return {"status": "ok", "message": "Heartbeat logged"}
    except Exception as e:
        logger.error(f"Failed to trigger heartbeat: {e}")
        return {"status": "error", "message": str(e)}
