"""Instrumentation API endpoints for observability."""

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from loguru import logger

from agent.api.auth import require_api_key
from agent.monitoring.instrumentation import get_instrumentation

# All endpoints in this router require API key authentication
router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/")
async def get_instrumentation_status() -> dict[str, Any]:
    """
    Get complete instrumentation status.

    Returns data reception stats, evaluation summary, and recent accepted signals.
    """
    try:
        inst = get_instrumentation()
        return inst.get_status()
    except Exception as e:
        logger.error(f"Failed to get instrumentation status: {e}")
        return {
            "error": str(e),
            "data_reception": None,
            "evaluations": None,
            "recent_accepted_signals": [],
        }


@router.get("/data-reception")
async def get_data_reception_stats() -> dict[str, Any]:
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
        return inst.get_data_stats()
    except Exception as e:
        logger.error(f"Failed to get data reception stats: {e}")
        return {"error": str(e)}


@router.get("/evaluations")
async def get_evaluations(
    strategy_name: str | None = Query(None, description="Filter by strategy name"),
    symbol: str | None = Query(None, description="Filter by symbol"),
    decision: str | None = Query(None, description="Filter by decision (accepted, rejected, skipped)"),
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
