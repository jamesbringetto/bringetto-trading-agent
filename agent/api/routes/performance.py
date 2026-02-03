"""Performance metrics API endpoints."""

from typing import Any

from fastapi import APIRouter, Query

from agent.api.main import get_agent_state

router = APIRouter()


@router.get("/summary")
async def get_performance_summary() -> dict[str, Any]:
    """Get overall performance summary."""
    state = get_agent_state()
    circuit_breaker = state.get("circuit_breaker")

    daily_stats = {}
    if circuit_breaker:
        daily_stats = circuit_breaker.get_daily_stats()

    broker = state.get("broker")
    account_info = None
    if broker:
        account_info = broker.get_account()

    return {
        "account": {
            "equity": float(account_info.equity) if account_info else 0,
            "cash": float(account_info.cash) if account_info else 0,
            "buying_power": float(account_info.buying_power) if account_info else 0,
        },
        "today": {
            "pnl": daily_stats.get("daily_pnl", 0),
            "trades": daily_stats.get("trades_today", 0),
            "max_trades": daily_stats.get("max_trades", 30),
        },
        "circuit_breaker": {
            "is_triggered": daily_stats.get("is_triggered", False),
            "trigger_reason": daily_stats.get("trigger_reason"),
        },
    }


@router.get("/daily")
async def get_daily_performance(
    days: int = Query(default=30, ge=1, le=365)
) -> list[dict[str, Any]]:
    """Get daily performance for the last N days."""
    # This would query from daily_summaries table
    return []


@router.get("/strategies")
async def get_strategy_performance() -> list[dict[str, Any]]:
    """Get performance metrics per strategy."""
    state = get_agent_state()
    strategies = state.get("strategies", [])

    # This would typically come from the database
    # For now, return basic info
    return [
        {
            "name": s.name,
            "type": s.strategy_type.value,
            "is_active": s.is_active,
            "open_positions": s.get_open_positions_count(),
            # These would come from strategy_performance table
            "trades_today": 0,
            "win_rate": None,
            "pnl_today": 0,
            "profit_factor": None,
        }
        for s in strategies
    ]


@router.get("/equity-curve")
async def get_equity_curve(
    period: str = Query(default="1M", regex="^(1D|1W|1M|3M|6M|1Y|ALL)$")
) -> list[dict[str, Any]]:
    """Get equity curve data for charting."""
    # This would query from daily_summaries or calculate from trades
    return []


@router.get("/metrics")
async def get_detailed_metrics() -> dict[str, Any]:
    """Get detailed trading metrics."""
    return {
        "total_trades": 0,
        "winning_trades": 0,
        "losing_trades": 0,
        "win_rate": None,
        "profit_factor": None,
        "sharpe_ratio": None,
        "max_drawdown": None,
        "avg_win": None,
        "avg_loss": None,
        "largest_win": None,
        "largest_loss": None,
        "avg_holding_time": None,
    }
