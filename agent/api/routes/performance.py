"""Performance metrics API endpoints."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from loguru import logger
from pydantic import BaseModel

from agent.api.auth import require_api_key
from agent.api.state import get_agent_state
from agent.config.constants import TradeStatus
from agent.database import get_session
from agent.database.repositories import (
    DailySummaryRepository,
    StrategyPerformanceRepository,
    StrategyRepository,
    TradeRepository,
)

# All endpoints in this router require API key authentication
router = APIRouter(dependencies=[Depends(require_api_key)])


class DailySummaryResponse(BaseModel):
    """Daily summary response model."""

    date: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float | None
    total_pnl: float
    total_pnl_pct: float | None
    best_trade: float | None
    worst_trade: float | None
    sharpe_ratio: float | None
    profit_factor: float | None
    account_balance: float | None


class StrategyPerformanceResponse(BaseModel):
    """Strategy performance response model."""

    name: str
    type: str
    is_active: bool
    open_positions: int
    trades_today: int
    win_rate: float | None
    pnl_today: float
    profit_factor: float | None


class EquityCurvePoint(BaseModel):
    """Equity curve data point."""

    date: str
    equity: float


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

    # Get open positions count
    open_positions = 0
    if broker:
        try:
            positions = broker.get_positions()
            open_positions = len(positions)
        except Exception:
            pass

    # Get trades_today from circuit breaker, fall back to DB
    trades_today = daily_stats.get("trades_today", 0)
    if not trades_today:
        try:
            with get_session() as session:
                trade_repo = TradeRepository(session)
                today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
                trades_today = trade_repo.get_trade_count(since=today_start)
        except Exception:
            pass

    # Get daily P&L from circuit breaker, fall back to equity change
    daily_pnl = daily_stats.get("daily_pnl", 0)
    if not daily_pnl and account_info:
        try:
            equity = float(account_info.equity)
            last_equity = float(account_info.last_equity)
            daily_pnl = equity - last_equity
        except Exception:
            pass

    return {
        "account": {
            "equity": float(account_info.equity) if account_info else 0,
            "cash": float(account_info.cash) if account_info else 0,
            "buying_power": float(account_info.buying_power) if account_info else 0,
        },
        "today": {
            "pnl": daily_pnl,
            "trades": trades_today,
            "max_trades": daily_stats.get("max_trades", 30),
            "open_positions": open_positions,
        },
        "circuit_breaker": {
            "is_triggered": daily_stats.get("is_triggered", False),
            "trigger_reason": daily_stats.get("trigger_reason"),
        },
    }


@router.get("/daily")
async def get_daily_performance(
    days: int = Query(default=30, ge=1, le=365),
) -> list[DailySummaryResponse]:
    """Get daily performance for the last N days."""
    try:
        with get_session() as session:
            repo = DailySummaryRepository(session)
            summaries = repo.get_history(days=days)

            return [
                DailySummaryResponse(
                    date=s.date.isoformat() if s.date else "",
                    total_trades=s.total_trades,
                    winning_trades=s.winning_trades,
                    losing_trades=s.losing_trades,
                    win_rate=float(s.win_rate) if s.win_rate else None,
                    total_pnl=float(s.total_pnl),
                    total_pnl_pct=float(s.total_pnl_pct) if s.total_pnl_pct else None,
                    best_trade=float(s.best_trade) if s.best_trade else None,
                    worst_trade=float(s.worst_trade) if s.worst_trade else None,
                    sharpe_ratio=float(s.sharpe_ratio) if s.sharpe_ratio else None,
                    profit_factor=float(s.profit_factor) if s.profit_factor else None,
                    account_balance=float(s.account_balance) if s.account_balance else None,
                )
                for s in summaries
            ]
    except Exception:
        return []


@router.get("/strategies")
async def get_strategy_performance() -> list[StrategyPerformanceResponse]:
    """Get performance metrics per strategy."""
    state = get_agent_state()
    strategies = state.get("strategies", [])

    # Build per-strategy unrealized P&L and open position counts from broker
    broker = state.get("broker")
    strategy_unrealized_pnl: dict[str, float] = {}
    strategy_open_positions: dict[str, int] = {}
    try:
        if broker:
            positions = broker.get_positions()
            position_pnl = {p.symbol: float(p.unrealized_pl) for p in positions}

            with get_session() as session:
                trade_repo = TradeRepository(session)
                open_trades = trade_repo.get_open_trades()
                strat_repo = StrategyRepository(session)
                for trade in open_trades:
                    strat = strat_repo.get_by_id(trade.strategy_id)
                    if strat:
                        name = strat.name
                        strategy_open_positions[name] = strategy_open_positions.get(name, 0) + 1
                        if trade.symbol in position_pnl:
                            strategy_unrealized_pnl[name] = (
                                strategy_unrealized_pnl.get(name, 0) + position_pnl[trade.symbol]
                            )
    except Exception:
        pass

    # Compute performance data from trades table directly
    strategy_performance: dict[str, dict] = {}
    db_strategy_list: list[Any] = []
    try:
        with get_session() as session:
            perf_repo = StrategyPerformanceRepository(session)
            strat_repo = StrategyRepository(session)
            trade_repo = TradeRepository(session)
            today = datetime.utcnow()

            db_strategies = strat_repo.get_all()
            logger.debug(f"Found {len(db_strategies)} DB strategies")

            for s in db_strategies:
                try:
                    # First try the StrategyPerformance table (pre-computed)
                    perf = perf_repo.get_for_date(s.id, today)
                    if perf:
                        strategy_performance[s.name] = {
                            "trades_today": perf.trades_count,
                            "win_rate": float(perf.win_rate) if perf.win_rate else None,
                            "pnl_today": float(perf.total_pnl),
                            "profit_factor": (
                                float(perf.profit_factor) if perf.profit_factor else None
                            ),
                        }
                        continue

                    # Fall back: compute from trades in Python
                    all_trades = trade_repo.get_trades_by_strategy(s.id, limit=10000)
                    if not all_trades and s.name not in strategy_open_positions:
                        continue

                    closed_trades = [t for t in all_trades if t.status == TradeStatus.CLOSED]
                    total_count = len(all_trades)
                    winning = [t for t in closed_trades if t.pnl and t.pnl > 0]
                    losing = [t for t in closed_trades if t.pnl and t.pnl < 0]

                    win_rate = None
                    if closed_trades:
                        win_rate = float(len(winning) / len(closed_trades) * 100)

                    gross_profit = sum(float(t.pnl) for t in winning) if winning else 0
                    gross_loss = sum(abs(float(t.pnl)) for t in losing) if losing else 0
                    profit_factor = None
                    if gross_loss > 0:
                        profit_factor = float(gross_profit / gross_loss)

                    realized_pnl = sum(float(t.pnl) for t in closed_trades if t.pnl)
                    unrealized_pnl = strategy_unrealized_pnl.get(s.name, 0)

                    strategy_performance[s.name] = {
                        "trades_today": total_count,
                        "win_rate": win_rate,
                        "pnl_today": realized_pnl + unrealized_pnl,
                        "profit_factor": profit_factor,
                    }
                    logger.debug(
                        f"Strategy '{s.name}': {total_count} trades, "
                        f"pnl={realized_pnl + unrealized_pnl:.2f}"
                    )
                except Exception as e:
                    logger.error(f"Error computing metrics for strategy '{s.name}': {e}")

            # If no in-memory strategies, use DB strategies as source
            if not strategies:
                db_strategy_list = [
                    {
                        "name": s.name,
                        "type": s.type.value if hasattr(s.type, "value") else str(s.type),
                        "is_active": s.is_active,
                    }
                    for s in db_strategies
                ]
    except Exception as e:
        logger.error(f"Error loading strategy performance data: {e}")

    # Use in-memory strategies if available, otherwise DB strategies
    if strategies:
        return [
            StrategyPerformanceResponse(
                name=s.name,
                type=s.strategy_type.value,
                is_active=s.is_active,
                open_positions=s.get_open_positions_count(),
                trades_today=strategy_performance.get(s.name, {}).get("trades_today", 0),
                win_rate=strategy_performance.get(s.name, {}).get("win_rate"),
                pnl_today=strategy_performance.get(s.name, {}).get("pnl_today", 0),
                profit_factor=strategy_performance.get(s.name, {}).get("profit_factor"),
            )
            for s in strategies
        ]
    else:
        return [
            StrategyPerformanceResponse(
                name=s["name"],
                type=s["type"],
                is_active=s["is_active"],
                open_positions=strategy_open_positions.get(s["name"], 0),
                trades_today=strategy_performance.get(s["name"], {}).get("trades_today", 0),
                win_rate=strategy_performance.get(s["name"], {}).get("win_rate"),
                pnl_today=strategy_performance.get(s["name"], {}).get("pnl_today", 0),
                profit_factor=strategy_performance.get(s["name"], {}).get("profit_factor"),
            )
            for s in db_strategy_list
        ]


@router.get("/equity-curve")
async def get_equity_curve(
    period: str = Query(default="1M", pattern="^(1D|1W|1M|3M|6M|1Y|ALL)$"),
) -> list[EquityCurvePoint]:
    """Get equity curve data for charting."""
    # Map period to days
    period_days = {
        "1D": 1,
        "1W": 7,
        "1M": 30,
        "3M": 90,
        "6M": 180,
        "1Y": 365,
        "ALL": 3650,  # ~10 years
    }
    days = period_days.get(period, 30)

    try:
        with get_session() as session:
            repo = DailySummaryRepository(session)
            summaries = repo.get_history(days=days)

            return [
                EquityCurvePoint(
                    date=s.date.isoformat() if s.date else "",
                    equity=float(s.account_balance) if s.account_balance else 0,
                )
                for s in reversed(summaries)  # Oldest first for charting
                if s.account_balance is not None
            ]
    except Exception:
        return []


@router.get("/metrics")
async def get_detailed_metrics() -> dict[str, Any]:
    """Get detailed trading metrics."""
    try:
        with get_session() as session:
            daily_repo = DailySummaryRepository(session)

            # Get recent summaries for aggregate metrics
            summaries = daily_repo.get_history(days=365)

            if summaries:
                total_pnl = sum(float(s.total_pnl) for s in summaries)
                winning_trades = sum(s.winning_trades for s in summaries)
                losing_trades = sum(s.losing_trades for s in summaries)
                total_count = winning_trades + losing_trades

                # Calculate aggregate metrics
                win_rate = (winning_trades / total_count * 100) if total_count > 0 else None

                # Get best/worst trades across all summaries
                best_trades = [float(s.best_trade) for s in summaries if s.best_trade]
                worst_trades = [float(s.worst_trade) for s in summaries if s.worst_trade]
                largest_win = max(best_trades) if best_trades else None
                largest_loss = min(worst_trades) if worst_trades else None

                # Average profit factor
                profit_factors = [float(s.profit_factor) for s in summaries if s.profit_factor]
                avg_profit_factor = (
                    sum(profit_factors) / len(profit_factors) if profit_factors else None
                )

                # Average Sharpe ratio
                sharpe_ratios = [float(s.sharpe_ratio) for s in summaries if s.sharpe_ratio]
                avg_sharpe = sum(sharpe_ratios) / len(sharpe_ratios) if sharpe_ratios else None

                # Max drawdown
                max_drawdowns = [float(s.max_drawdown) for s in summaries if s.max_drawdown]
                max_dd = min(max_drawdowns) if max_drawdowns else None

                return {
                    "total_trades": total_count,
                    "winning_trades": winning_trades,
                    "losing_trades": losing_trades,
                    "win_rate": win_rate,
                    "profit_factor": avg_profit_factor,
                    "sharpe_ratio": avg_sharpe,
                    "max_drawdown": max_dd,
                    "total_pnl": total_pnl,
                    "largest_win": largest_win,
                    "largest_loss": largest_loss,
                    "avg_win": None,  # Would need to calculate from trades
                    "avg_loss": None,
                    "avg_holding_time": None,
                }
    except Exception:
        pass

    # Return defaults if database unavailable
    return {
        "total_trades": 0,
        "winning_trades": 0,
        "losing_trades": 0,
        "win_rate": None,
        "profit_factor": None,
        "sharpe_ratio": None,
        "max_drawdown": None,
        "total_pnl": 0,
        "avg_win": None,
        "avg_loss": None,
        "largest_win": None,
        "largest_loss": None,
        "avg_holding_time": None,
    }
