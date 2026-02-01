"""Trading control API endpoints (kill switch, emergency stops)."""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from loguru import logger

from agent.api.main import get_agent_state, set_agent_state


router = APIRouter()


class KillSwitchResponse(BaseModel):
    """Kill switch response."""

    success: bool
    message: str
    positions_closed: int
    orders_cancelled: int


class TradingStatusResponse(BaseModel):
    """Trading status response."""

    is_running: bool
    can_trade: bool
    reason: str
    circuit_breaker_active: bool


@router.post("/kill-switch", response_model=KillSwitchResponse)
async def activate_kill_switch() -> KillSwitchResponse:
    """
    EMERGENCY: Stop all trading and close all positions.

    This will:
    1. Disable all strategies
    2. Cancel all open orders
    3. Close all positions
    """
    logger.warning("KILL SWITCH ACTIVATED")

    state = get_agent_state()
    broker = state.get("broker")
    strategies = state.get("strategies", [])

    # Disable all strategies
    for strategy in strategies:
        strategy.disable("Kill switch activated")

    positions_closed = 0
    orders_cancelled = 0

    if broker:
        try:
            # Cancel all orders
            broker.cancel_all_orders()
            orders_cancelled = len(broker.get_open_orders())
        except Exception as e:
            logger.error(f"Error cancelling orders: {e}")

        try:
            # Close all positions
            positions = broker.get_positions()
            positions_closed = len(positions)
            await broker.close_all_positions()
        except Exception as e:
            logger.error(f"Error closing positions: {e}")

    set_agent_state("is_running", False)

    return KillSwitchResponse(
        success=True,
        message="Kill switch activated - all trading stopped",
        positions_closed=positions_closed,
        orders_cancelled=orders_cancelled,
    )


@router.get("/status", response_model=TradingStatusResponse)
async def get_trading_status() -> TradingStatusResponse:
    """Get current trading status."""
    state = get_agent_state()
    circuit_breaker = state.get("circuit_breaker")
    is_running = state.get("is_running", False)

    can_trade = True
    reason = "Trading enabled"
    cb_active = False

    if circuit_breaker:
        can_trade, reason = circuit_breaker.can_trade()
        cb_state = circuit_breaker.get_state()
        cb_active = cb_state.is_triggered

    if not is_running:
        can_trade = False
        reason = "Agent is not running"

    return TradingStatusResponse(
        is_running=is_running,
        can_trade=can_trade,
        reason=reason,
        circuit_breaker_active=cb_active,
    )


@router.post("/pause")
async def pause_trading() -> dict[str, Any]:
    """Pause trading (keeps positions open, stops new trades)."""
    state = get_agent_state()
    strategies = state.get("strategies", [])

    for strategy in strategies:
        strategy.disable("Trading paused via API")

    set_agent_state("is_running", False)

    logger.info("Trading paused via API")

    return {
        "success": True,
        "message": "Trading paused - no new trades will be opened",
        "strategies_disabled": len(strategies),
    }


@router.post("/resume")
async def resume_trading() -> dict[str, Any]:
    """Resume trading after pause."""
    state = get_agent_state()
    strategies = state.get("strategies", [])
    circuit_breaker = state.get("circuit_breaker")

    # Check circuit breaker first
    if circuit_breaker:
        can_trade, reason = circuit_breaker.can_trade()
        if not can_trade:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot resume: {reason}",
            )

    for strategy in strategies:
        strategy.enable()

    set_agent_state("is_running", True)

    logger.info("Trading resumed via API")

    return {
        "success": True,
        "message": "Trading resumed",
        "strategies_enabled": len(strategies),
    }


@router.post("/circuit-breaker/reset")
async def reset_circuit_breaker() -> dict[str, Any]:
    """
    Manually reset the circuit breaker.

    WARNING: Use with extreme caution. This overrides safety limits.
    """
    state = get_agent_state()
    circuit_breaker = state.get("circuit_breaker")

    if not circuit_breaker:
        raise HTTPException(status_code=503, detail="Circuit breaker not initialized")

    circuit_breaker.manual_reset()

    logger.warning("Circuit breaker manually reset via API")

    return {
        "success": True,
        "message": "Circuit breaker reset - trading limits restored",
        "warning": "Safety limits have been reset. Monitor closely.",
    }
