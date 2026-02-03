"""Strategy management API endpoints."""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent.api.main import get_agent_state

router = APIRouter()


class StrategyResponse(BaseModel):
    """Strategy response model."""

    name: str
    type: str
    version: str
    is_active: bool
    is_experimental: bool
    parameters: dict[str, Any]
    open_positions: int


class StrategyToggleRequest(BaseModel):
    """Request to toggle a strategy."""

    is_active: bool


@router.get("/")
async def list_strategies() -> list[dict[str, Any]]:
    """List all strategies and their status."""
    state = get_agent_state()
    strategies = state.get("strategies", [])

    return [
        {
            "name": s.name,
            "type": s.strategy_type.value,
            "version": s.version,
            "is_active": s.is_active,
            "parameters": s.parameters,
            "open_positions": s.get_open_positions_count(),
        }
        for s in strategies
    ]


@router.get("/{strategy_name}")
async def get_strategy(strategy_name: str) -> dict[str, Any]:
    """Get details of a specific strategy."""
    state = get_agent_state()
    strategies = state.get("strategies", [])

    for s in strategies:
        if s.name.lower().replace(" ", "_") == strategy_name.lower().replace(" ", "_"):
            return {
                "name": s.name,
                "type": s.strategy_type.value,
                "version": s.version,
                "is_active": s.is_active,
                "parameters": s.parameters,
                "open_positions": s.get_open_positions_count(),
            }

    raise HTTPException(status_code=404, detail="Strategy not found")


@router.patch("/{strategy_name}/toggle")
async def toggle_strategy(strategy_name: str, request: StrategyToggleRequest) -> dict[str, Any]:
    """Enable or disable a strategy."""
    state = get_agent_state()
    strategies = state.get("strategies", [])

    for s in strategies:
        if s.name.lower().replace(" ", "_") == strategy_name.lower().replace(" ", "_"):
            if request.is_active:
                s.enable()
            else:
                s.disable("Manually disabled via API")

            return {
                "name": s.name,
                "is_active": s.is_active,
                "message": f"Strategy {'enabled' if request.is_active else 'disabled'}",
            }

    raise HTTPException(status_code=404, detail="Strategy not found")


@router.patch("/{strategy_name}/parameters")
async def update_strategy_parameters(
    strategy_name: str, parameters: dict[str, Any]
) -> dict[str, Any]:
    """Update strategy parameters."""
    state = get_agent_state()
    strategies = state.get("strategies", [])

    for s in strategies:
        if s.name.lower().replace(" ", "_") == strategy_name.lower().replace(" ", "_"):
            # Only update allowed parameters
            allowed_updates = {
                "stop_loss_pct",
                "take_profit_pct",
                "position_size_pct",
            }

            for key, value in parameters.items():
                if key in allowed_updates:
                    s.parameters[key] = value

            return {
                "name": s.name,
                "parameters": s.parameters,
                "message": "Parameters updated",
            }

    raise HTTPException(status_code=404, detail="Strategy not found")
