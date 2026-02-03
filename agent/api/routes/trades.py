"""Trade-related API endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from agent.api.auth import require_api_key
from agent.api.state import get_agent_state

# All endpoints in this router require API key authentication
router = APIRouter(dependencies=[Depends(require_api_key)])


class TradeResponse(BaseModel):
    """Trade response model."""

    id: str
    symbol: str
    side: str
    entry_price: float
    exit_price: float | None
    quantity: float
    pnl: float | None
    pnl_percent: float | None
    status: str
    entry_time: str
    exit_time: str | None
    strategy_name: str


class ActiveTradeResponse(BaseModel):
    """Active trade response model."""

    symbol: str
    side: str
    entry_price: float
    current_price: float
    quantity: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    stop_loss: float
    take_profit: float
    strategy_name: str
    entry_time: str
    holding_time_seconds: int


@router.get("/active")
async def get_active_trades() -> list[dict[str, Any]]:
    """Get all active/open trades."""
    state = get_agent_state()
    broker = state.get("broker")

    if not broker:
        raise HTTPException(status_code=503, detail="Broker not initialized")

    positions = broker.get_positions()

    return [
        {
            "symbol": p.symbol,
            "side": p.side,
            "quantity": float(p.qty),
            "entry_price": float(p.avg_entry_price),
            "market_value": float(p.market_value),
            "unrealized_pnl": float(p.unrealized_pl),
            "unrealized_pnl_pct": float(p.unrealized_plpc) * 100,
        }
        for p in positions
    ]


@router.get("/history")
async def get_trade_history(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    strategy: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
) -> dict[str, Any]:
    """Get trade history with pagination and filters."""
    # This would query from database
    # For now, return placeholder
    return {
        "trades": [],
        "total": 0,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{trade_id}")
async def get_trade(trade_id: str) -> dict[str, Any]:
    """Get details of a specific trade."""
    # This would query from database
    raise HTTPException(status_code=404, detail="Trade not found")


@router.get("/{trade_id}/decisions")
async def get_trade_decisions(trade_id: str) -> list[dict[str, Any]]:
    """Get all decisions/reasoning for a specific trade."""
    # This would query trade_decisions table
    return []
