"""Trade-related API endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from agent.api.auth import require_api_key
from agent.api.state import get_agent_state
from agent.database import get_session
from agent.database.repositories import TradeDecisionRepository, TradeRepository

# All endpoints in this router require API key authentication
router = APIRouter(dependencies=[Depends(require_api_key)])


class TradeResponse(BaseModel):
    """Trade response model."""

    id: str
    timestamp: str
    symbol: str
    strategy_id: str
    strategy_name: str
    side: str
    entry_price: float
    exit_price: float | None
    quantity: float
    pnl: float | None
    pnl_percent: float | None
    commission: float
    status: str
    entry_time: str
    exit_time: str | None
    holding_time_seconds: int | None
    stop_loss: float
    take_profit: float


class ActiveTradeResponse(BaseModel):
    """Active trade response model."""

    symbol: str
    side: str
    entry_price: float
    current_price: float
    quantity: float
    market_value: float
    unrealized_pnl: float
    unrealized_pnl_pct: float


class TradeDecisionResponse(BaseModel):
    """Trade decision response model."""

    id: str
    trade_id: str | None
    timestamp: str
    decision_type: str
    strategy_name: str
    symbol: str
    price: float
    reasoning_text: str
    confidence_score: float | None
    outcome: str | None
    what_worked: str | None
    what_failed: str | None


@router.get("/active")
async def get_active_trades() -> list[ActiveTradeResponse]:
    """Get all active/open positions from the broker."""
    state = get_agent_state()
    broker = state.get("broker")

    if not broker:
        raise HTTPException(status_code=503, detail="Broker not initialized")

    positions = broker.get_positions()

    return [
        ActiveTradeResponse(
            symbol=p.symbol,
            side=p.side,
            quantity=float(p.qty),
            entry_price=float(p.avg_entry_price),
            current_price=float(p.current_price)
            if hasattr(p, "current_price")
            else float(p.avg_entry_price),
            market_value=float(p.market_value),
            unrealized_pnl=float(p.unrealized_pl),
            unrealized_pnl_pct=float(p.unrealized_plpc) * 100,
        )
        for p in positions
    ]


@router.get("/history")
async def get_trade_history(
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    strategy: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
) -> list[TradeResponse]:
    """Get trade history with pagination and filters."""
    try:
        with get_session() as session:
            repo = TradeRepository(session)
            trades = repo.get_history(
                limit=limit,
                offset=offset,
                strategy_name=strategy,
                symbol=symbol,
            )

            return [
                TradeResponse(
                    id=str(t.id),
                    timestamp=t.timestamp.isoformat() if t.timestamp else "",
                    symbol=t.symbol,
                    strategy_id=str(t.strategy_id),
                    strategy_name=t.strategy.name if t.strategy else "Unknown",
                    side=t.side.value if hasattr(t.side, "value") else str(t.side),
                    entry_price=float(t.entry_price),
                    exit_price=float(t.exit_price) if t.exit_price else None,
                    quantity=float(t.quantity),
                    pnl=float(t.pnl) if t.pnl else None,
                    pnl_percent=float(t.pnl_percent) if t.pnl_percent else None,
                    commission=float(t.commission) if t.commission else 0,
                    status=t.status.value if hasattr(t.status, "value") else str(t.status),
                    entry_time=t.entry_time.isoformat() if t.entry_time else "",
                    exit_time=t.exit_time.isoformat() if t.exit_time else None,
                    holding_time_seconds=t.holding_time_seconds,
                    stop_loss=float(t.stop_loss),
                    take_profit=float(t.take_profit),
                )
                for t in trades
            ]
    except Exception:
        # If database isn't available, return empty list
        return []


@router.get("/{trade_id}")
async def get_trade(trade_id: str) -> TradeResponse:
    """Get details of a specific trade."""
    try:
        trade_uuid = UUID(trade_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid trade ID format")

    try:
        with get_session() as session:
            repo = TradeRepository(session)
            trade = repo.get_by_id(trade_uuid)

            if not trade:
                raise HTTPException(status_code=404, detail="Trade not found")

            return TradeResponse(
                id=str(trade.id),
                timestamp=trade.timestamp.isoformat() if trade.timestamp else "",
                symbol=trade.symbol,
                strategy_id=str(trade.strategy_id),
                strategy_name=trade.strategy.name if trade.strategy else "Unknown",
                side=trade.side.value if hasattr(trade.side, "value") else str(trade.side),
                entry_price=float(trade.entry_price),
                exit_price=float(trade.exit_price) if trade.exit_price else None,
                quantity=float(trade.quantity),
                pnl=float(trade.pnl) if trade.pnl else None,
                pnl_percent=float(trade.pnl_percent) if trade.pnl_percent else None,
                commission=float(trade.commission) if trade.commission else 0,
                status=trade.status.value if hasattr(trade.status, "value") else str(trade.status),
                entry_time=trade.entry_time.isoformat() if trade.entry_time else "",
                exit_time=trade.exit_time.isoformat() if trade.exit_time else None,
                holding_time_seconds=trade.holding_time_seconds,
                stop_loss=float(trade.stop_loss),
                take_profit=float(trade.take_profit),
            )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="Trade not found")


@router.get("/{trade_id}/decisions")
async def get_trade_decisions(trade_id: str) -> list[TradeDecisionResponse]:
    """Get all decisions/reasoning for a specific trade."""
    try:
        trade_uuid = UUID(trade_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid trade ID format")

    try:
        with get_session() as session:
            repo = TradeDecisionRepository(session)
            decisions = repo.get_by_trade_id(trade_uuid)

            return [
                TradeDecisionResponse(
                    id=str(d.id),
                    trade_id=str(d.trade_id) if d.trade_id else None,
                    timestamp=d.timestamp.isoformat() if d.timestamp else "",
                    decision_type=d.decision_type.value
                    if hasattr(d.decision_type, "value")
                    else str(d.decision_type),
                    strategy_name=d.strategy_name,
                    symbol=d.symbol,
                    price=float(d.price),
                    reasoning_text=d.reasoning_text,
                    confidence_score=float(d.confidence_score) if d.confidence_score else None,
                    outcome=d.outcome,
                    what_worked=d.what_worked,
                    what_failed=d.what_failed,
                )
                for d in decisions
            ]
    except Exception:
        return []
