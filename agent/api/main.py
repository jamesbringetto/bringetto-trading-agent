"""FastAPI application for the trading agent dashboard API."""

import asyncio
import contextlib
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from pydantic import BaseModel

from agent.api.routes import (
    analytics,
    controls,
    instrumentation,
    market,
    performance,
    strategies,
    trades,
)
from agent.api.state import get_agent_state, set_agent_state
from agent.config.settings import get_settings


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    timestamp: str
    environment: str
    database: bool
    alpaca: bool
    active_strategies: int
    open_positions: int


# Re-export for backwards compatibility
__all__ = ["app", "create_app", "get_agent_state", "set_agent_state"]


# Global reference to agent task for shutdown
_agent_task: asyncio.Task | None = None
_agent_instance = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler - starts trading agent as background task."""
    global _agent_task, _agent_instance

    logger.info("Starting Trading Agent API...")

    # Import here to avoid circular imports
    from agent.main import TradingAgent

    # Create and start the trading agent as a background task
    logger.info("Initializing trading agent in API process...")
    _agent_instance = TradingAgent()

    _agent_task = asyncio.create_task(
        _agent_instance.run(),
        name="trading_agent"
    )

    logger.info("Trading agent started as background task")

    yield

    # Shutdown
    logger.info("Shutting down Trading Agent API...")
    if _agent_instance:
        await _agent_instance.shutdown()
    if _agent_task and not _agent_task.done():
        _agent_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _agent_task
    logger.info("Trading agent shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Bringetto Trading Agent API",
        description="API for the AI-powered day trading agent",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(trades.router, prefix="/api/trades", tags=["trades"])
    app.include_router(strategies.router, prefix="/api/strategies", tags=["strategies"])
    app.include_router(performance.router, prefix="/api/performance", tags=["performance"])
    app.include_router(controls.router, prefix="/api/controls", tags=["controls"])
    app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
    app.include_router(market.router, prefix="/api/market", tags=["market"])
    app.include_router(
        instrumentation.router, prefix="/api/instrumentation", tags=["instrumentation"]
    )

    @app.get("/", tags=["root"])
    async def root():
        """Root endpoint."""
        return {
            "name": "Bringetto Trading Agent",
            "version": "0.1.0",
            "status": "running",
            "environment": settings.environment,
        }

    @app.get("/health", response_model=HealthResponse, tags=["health"])
    async def health_check():
        """
        Health check endpoint for Railway/monitoring.

        Returns status of:
        - Database connection
        - Alpaca connection
        - Active strategies
        - Open positions
        """
        state = get_agent_state()

        # Check database
        db_healthy = True
        try:
            from sqlalchemy import text

            from agent.database import get_session

            with get_session() as session:
                session.execute(text("SELECT 1"))
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            db_healthy = False

        # Check Alpaca
        alpaca_healthy = False
        if state.get("broker"):
            try:
                account = state["broker"].get_account()
                alpaca_healthy = account is not None
            except Exception as e:
                logger.error(f"Alpaca health check failed: {e}")

        # Count active strategies
        active_strategies = len([s for s in state.get("strategies", []) if s.is_active])

        # Count open positions
        open_positions = 0
        if state.get("broker"):
            try:
                positions = state["broker"].get_positions()
                open_positions = len(positions)
            except Exception:
                pass

        status = "healthy" if (db_healthy and alpaca_healthy) else "unhealthy"

        return HealthResponse(
            status=status,
            timestamp=datetime.utcnow().isoformat(),
            environment=settings.environment,
            database=db_healthy,
            alpaca=alpaca_healthy,
            active_strategies=active_strategies,
            open_positions=open_positions,
        )

    return app


# Create the app instance
app = create_app()
