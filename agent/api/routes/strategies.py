"""Strategy management API endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel

from agent.api.auth import require_api_key
from agent.api.state import get_agent_state
from agent.database import get_session
from agent.database.repositories import StrategyRepository

# All endpoints in this router require API key authentication
router = APIRouter(dependencies=[Depends(require_api_key)])


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
    """List all strategies and their status from database."""
    try:
        with get_session() as session:
            repo = StrategyRepository(session)
            strategies = repo.get_all()

            return [
                {
                    "name": s.name,
                    "type": s.type.value if hasattr(s.type, "value") else str(s.type),
                    "version": s.version,
                    "is_active": s.is_active,
                    "is_experimental": s.is_experimental,
                    "parameters": s.parameters or {},
                    "open_positions": 0,  # Would need broker to get real count
                }
                for s in strategies
            ]
    except Exception as e:
        logger.error(f"Failed to fetch strategies from database: {e}")
        # Fallback to in-memory state if available
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
    try:
        with get_session() as session:
            repo = StrategyRepository(session)
            strategy = repo.get_by_name(strategy_name.replace("_", " "))

            if not strategy:
                # Try with underscores replaced
                strategies = repo.get_all()
                for s in strategies:
                    if s.name.lower().replace(" ", "_") == strategy_name.lower().replace(" ", "_"):
                        strategy = s
                        break

            if strategy:
                return {
                    "name": strategy.name,
                    "type": strategy.type.value
                    if hasattr(strategy.type, "value")
                    else str(strategy.type),
                    "version": strategy.version,
                    "is_active": strategy.is_active,
                    "is_experimental": strategy.is_experimental,
                    "parameters": strategy.parameters or {},
                    "open_positions": 0,
                }

    except Exception as e:
        logger.error(f"Failed to fetch strategy from database: {e}")

    raise HTTPException(status_code=404, detail="Strategy not found")


@router.patch("/{strategy_name}/toggle")
async def toggle_strategy(strategy_name: str, request: StrategyToggleRequest) -> dict[str, Any]:
    """Enable or disable a strategy."""
    try:
        with get_session() as session:
            repo = StrategyRepository(session)

            # Find strategy by name
            strategy = repo.get_by_name(strategy_name.replace("_", " "))
            if not strategy:
                strategies = repo.get_all()
                for s in strategies:
                    if s.name.lower().replace(" ", "_") == strategy_name.lower().replace(" ", "_"):
                        strategy = s
                        break

            if strategy:
                strategy.is_active = request.is_active
                if not request.is_active:
                    from datetime import datetime

                    strategy.disabled_reason = "Manually disabled via API"
                    strategy.disabled_at = datetime.now()
                else:
                    strategy.disabled_reason = None
                    strategy.disabled_at = None

                session.commit()

                return {
                    "name": strategy.name,
                    "is_active": strategy.is_active,
                    "message": f"Strategy {'enabled' if request.is_active else 'disabled'}",
                }

    except Exception as e:
        logger.error(f"Failed to toggle strategy: {e}")

    raise HTTPException(status_code=404, detail="Strategy not found")


@router.patch("/{strategy_name}/parameters")
async def update_strategy_parameters(
    strategy_name: str, parameters: dict[str, Any]
) -> dict[str, Any]:
    """Update strategy parameters."""
    try:
        with get_session() as session:
            repo = StrategyRepository(session)

            # Find strategy by name
            strategy = repo.get_by_name(strategy_name.replace("_", " "))
            if not strategy:
                strategies = repo.get_all()
                for s in strategies:
                    if s.name.lower().replace(" ", "_") == strategy_name.lower().replace(" ", "_"):
                        strategy = s
                        break

            if strategy:
                # Only update allowed parameters
                allowed_updates = {
                    "stop_loss_pct",
                    "take_profit_pct",
                    "position_size_pct",
                }

                current_params = strategy.parameters or {}
                for key, value in parameters.items():
                    if key in allowed_updates:
                        current_params[key] = value

                strategy.parameters = current_params
                session.commit()

                return {
                    "name": strategy.name,
                    "parameters": strategy.parameters,
                    "message": "Parameters updated",
                }

    except Exception as e:
        logger.error(f"Failed to update strategy parameters: {e}")

    raise HTTPException(status_code=404, detail="Strategy not found")
