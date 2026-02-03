"""Analytics API endpoints for deep performance analysis."""

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import and_, desc, extract, func, select

from agent.api.auth import require_api_key
from agent.config.constants import TradeStatus
from agent.database import get_session
from agent.database.models import (
    DailySummary,
    Strategy,
    StrategyPerformance,
    Trade,
)

# All endpoints in this router require API key authentication
router = APIRouter(dependencies=[Depends(require_api_key)])


class TimeOfDayPerformance(BaseModel):
    """Performance metrics for a specific hour."""

    hour: int
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float | None
    total_pnl: float
    avg_pnl: float | None


class SymbolPerformance(BaseModel):
    """Performance metrics for a specific symbol."""

    symbol: str
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float | None
    total_pnl: float
    avg_pnl: float | None
    largest_win: float | None
    largest_loss: float | None


class StrategyComparison(BaseModel):
    """Strategy comparison data."""

    name: str
    strategy_type: str
    is_active: bool
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float | None
    total_pnl: float
    profit_factor: float | None
    sharpe_ratio: float | None
    max_drawdown: float | None
    avg_holding_time_seconds: float | None


class RiskMetrics(BaseModel):
    """Risk-adjusted performance metrics."""

    sharpe_ratio: float | None
    sortino_ratio: float | None
    max_drawdown: float | None
    max_drawdown_duration_days: int | None
    calmar_ratio: float | None
    win_rate: float | None
    profit_factor: float | None
    avg_win: float | None
    avg_loss: float | None
    expectancy: float | None
    risk_reward_ratio: float | None


class PnLCurvePoint(BaseModel):
    """P&L curve data point."""

    date: str
    cumulative_pnl: float
    daily_pnl: float
    trade_count: int


@router.get("/time-of-day")
async def get_time_of_day_performance(
    days: int = Query(default=30, ge=1, le=365),
) -> list[TimeOfDayPerformance]:
    """Get win rate and P&L by hour of day."""
    try:
        with get_session() as session:
            since = datetime.utcnow() - timedelta(days=days)

            # Query trades grouped by hour
            results = session.execute(
                select(
                    extract("hour", Trade.entry_time).label("hour"),
                    func.count(Trade.id).label("total_trades"),
                    func.sum(
                        func.case((Trade.pnl > 0, 1), else_=0)
                    ).label("winning_trades"),
                    func.sum(
                        func.case((Trade.pnl < 0, 1), else_=0)
                    ).label("losing_trades"),
                    func.sum(Trade.pnl).label("total_pnl"),
                )
                .where(
                    and_(
                        Trade.entry_time >= since,
                        Trade.status == TradeStatus.CLOSED,
                    )
                )
                .group_by(extract("hour", Trade.entry_time))
                .order_by(extract("hour", Trade.entry_time))
            ).all()

            return [
                TimeOfDayPerformance(
                    hour=int(r.hour or 0),
                    total_trades=r.total_trades or 0,
                    winning_trades=r.winning_trades or 0,
                    losing_trades=r.losing_trades or 0,
                    win_rate=(
                        (r.winning_trades / r.total_trades * 100)
                        if r.total_trades
                        else None
                    ),
                    total_pnl=float(r.total_pnl or 0),
                    avg_pnl=(
                        float(r.total_pnl / r.total_trades)
                        if r.total_trades and r.total_pnl
                        else None
                    ),
                )
                for r in results
            ]
    except Exception:
        return []


@router.get("/symbol-performance")
async def get_symbol_performance(
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[SymbolPerformance]:
    """Get performance metrics by symbol."""
    try:
        with get_session() as session:
            since = datetime.utcnow() - timedelta(days=days)

            results = session.execute(
                select(
                    Trade.symbol,
                    func.count(Trade.id).label("total_trades"),
                    func.sum(
                        func.case((Trade.pnl > 0, 1), else_=0)
                    ).label("winning_trades"),
                    func.sum(
                        func.case((Trade.pnl < 0, 1), else_=0)
                    ).label("losing_trades"),
                    func.sum(Trade.pnl).label("total_pnl"),
                    func.max(
                        func.case((Trade.pnl > 0, Trade.pnl), else_=None)
                    ).label("largest_win"),
                    func.min(
                        func.case((Trade.pnl < 0, Trade.pnl), else_=None)
                    ).label("largest_loss"),
                )
                .where(
                    and_(
                        Trade.entry_time >= since,
                        Trade.status == TradeStatus.CLOSED,
                    )
                )
                .group_by(Trade.symbol)
                .order_by(desc(func.sum(Trade.pnl)))
                .limit(limit)
            ).all()

            return [
                SymbolPerformance(
                    symbol=r.symbol,
                    total_trades=r.total_trades or 0,
                    winning_trades=r.winning_trades or 0,
                    losing_trades=r.losing_trades or 0,
                    win_rate=(
                        (r.winning_trades / r.total_trades * 100)
                        if r.total_trades
                        else None
                    ),
                    total_pnl=float(r.total_pnl or 0),
                    avg_pnl=(
                        float(r.total_pnl / r.total_trades)
                        if r.total_trades and r.total_pnl
                        else None
                    ),
                    largest_win=float(r.largest_win) if r.largest_win else None,
                    largest_loss=float(r.largest_loss) if r.largest_loss else None,
                )
                for r in results
            ]
    except Exception:
        return []


@router.get("/strategy-comparison")
async def get_strategy_comparison(
    days: int = Query(default=30, ge=1, le=365),
) -> list[StrategyComparison]:
    """Get comprehensive strategy comparison metrics."""
    try:
        with get_session() as session:
            since = datetime.utcnow() - timedelta(days=days)

            # Get all strategies
            strategies = list(session.execute(select(Strategy)).scalars().all())

            results = []
            for strategy in strategies:
                # Get trades for this strategy
                trade_stats = session.execute(
                    select(
                        func.count(Trade.id).label("total_trades"),
                        func.sum(
                            func.case((Trade.pnl > 0, 1), else_=0)
                        ).label("winning_trades"),
                        func.sum(
                            func.case((Trade.pnl < 0, 1), else_=0)
                        ).label("losing_trades"),
                        func.sum(Trade.pnl).label("total_pnl"),
                        func.sum(
                            func.case((Trade.pnl > 0, Trade.pnl), else_=0)
                        ).label("gross_profit"),
                        func.sum(
                            func.case(
                                (Trade.pnl < 0, func.abs(Trade.pnl)), else_=0
                            )
                        ).label("gross_loss"),
                        func.avg(Trade.holding_time_seconds).label("avg_holding_time"),
                    )
                    .where(
                        and_(
                            Trade.strategy_id == strategy.id,
                            Trade.entry_time >= since,
                            Trade.status == TradeStatus.CLOSED,
                        )
                    )
                ).first()

                if not trade_stats:
                    continue

                # Calculate profit factor
                profit_factor = None
                if trade_stats.gross_loss and trade_stats.gross_loss > 0:
                    profit_factor = float(
                        trade_stats.gross_profit / trade_stats.gross_loss
                    ) if trade_stats.gross_profit else 0

                # Get performance metrics from strategy_performance table
                perf_records = list(
                    session.execute(
                        select(StrategyPerformance)
                        .where(
                            and_(
                                StrategyPerformance.strategy_id == strategy.id,
                                StrategyPerformance.date >= since,
                            )
                        )
                    )
                    .scalars()
                    .all()
                )

                sharpe_ratios = [
                    float(p.sharpe_ratio)
                    for p in perf_records
                    if p.sharpe_ratio
                ]
                max_drawdowns = [
                    float(p.max_drawdown)
                    for p in perf_records
                    if p.max_drawdown
                ]

                results.append(
                    StrategyComparison(
                        name=strategy.name,
                        strategy_type=strategy.type.value if strategy.type else "unknown",
                        is_active=strategy.is_active,
                        total_trades=trade_stats.total_trades or 0,
                        winning_trades=trade_stats.winning_trades or 0,
                        losing_trades=trade_stats.losing_trades or 0,
                        win_rate=(
                            (trade_stats.winning_trades / trade_stats.total_trades * 100)
                            if trade_stats.total_trades
                            else None
                        ),
                        total_pnl=float(trade_stats.total_pnl or 0),
                        profit_factor=profit_factor,
                        sharpe_ratio=(
                            sum(sharpe_ratios) / len(sharpe_ratios)
                            if sharpe_ratios
                            else None
                        ),
                        max_drawdown=min(max_drawdowns) if max_drawdowns else None,
                        avg_holding_time_seconds=(
                            float(trade_stats.avg_holding_time)
                            if trade_stats.avg_holding_time
                            else None
                        ),
                    )
                )

            return sorted(results, key=lambda x: x.total_pnl, reverse=True)
    except Exception:
        return []


@router.get("/risk-metrics")
async def get_risk_metrics(
    days: int = Query(default=30, ge=1, le=365),
) -> RiskMetrics:
    """Get comprehensive risk-adjusted metrics."""
    try:
        with get_session() as session:
            since = datetime.utcnow() - timedelta(days=days)

            # Get daily summaries for calculations
            summaries = list(
                session.execute(
                    select(DailySummary)
                    .where(DailySummary.date >= since)
                    .order_by(DailySummary.date)
                )
                .scalars()
                .all()
            )

            # Get all closed trades
            trades = list(
                session.execute(
                    select(Trade)
                    .where(
                        and_(
                            Trade.entry_time >= since,
                            Trade.status == TradeStatus.CLOSED,
                        )
                    )
                )
                .scalars()
                .all()
            )

            if not trades:
                return RiskMetrics(
                    sharpe_ratio=None,
                    sortino_ratio=None,
                    max_drawdown=None,
                    max_drawdown_duration_days=None,
                    calmar_ratio=None,
                    win_rate=None,
                    profit_factor=None,
                    avg_win=None,
                    avg_loss=None,
                    expectancy=None,
                    risk_reward_ratio=None,
                )

            # Calculate basic metrics
            total_trades = len(trades)
            winning_trades = [t for t in trades if t.pnl and t.pnl > 0]
            losing_trades = [t for t in trades if t.pnl and t.pnl < 0]

            win_rate = len(winning_trades) / total_trades * 100 if total_trades else None

            avg_win = (
                sum(float(t.pnl) for t in winning_trades) / len(winning_trades)
                if winning_trades
                else None
            )
            avg_loss = (
                abs(sum(float(t.pnl) for t in losing_trades)) / len(losing_trades)
                if losing_trades
                else None
            )

            # Profit factor
            gross_profit = sum(float(t.pnl) for t in winning_trades) if winning_trades else 0
            gross_loss = abs(sum(float(t.pnl) for t in losing_trades)) if losing_trades else 0
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else None

            # Expectancy
            expectancy = None
            if avg_win and avg_loss and win_rate:
                win_prob = win_rate / 100
                loss_prob = 1 - win_prob
                expectancy = (win_prob * avg_win) - (loss_prob * avg_loss)

            # Risk/reward ratio
            risk_reward = avg_win / avg_loss if avg_win and avg_loss else None

            # Sharpe ratio from daily summaries
            if summaries:
                daily_returns = [
                    float(s.total_pnl_pct) for s in summaries if s.total_pnl_pct
                ]
                if daily_returns:
                    import statistics
                    mean_return = statistics.mean(daily_returns)
                    if len(daily_returns) > 1:
                        std_dev = statistics.stdev(daily_returns)
                        sharpe = (mean_return * 252**0.5) / std_dev if std_dev else None
                    else:
                        sharpe = None
                else:
                    sharpe = None

                # Max drawdown
                max_drawdowns = [
                    float(s.max_drawdown) for s in summaries if s.max_drawdown
                ]
                max_dd = min(max_drawdowns) if max_drawdowns else None
            else:
                sharpe = None
                max_dd = None

            return RiskMetrics(
                sharpe_ratio=sharpe,
                sortino_ratio=None,  # Would need downside deviation
                max_drawdown=max_dd,
                max_drawdown_duration_days=None,  # Would need equity curve analysis
                calmar_ratio=None,  # annualized_return / max_drawdown
                win_rate=win_rate,
                profit_factor=profit_factor,
                avg_win=avg_win,
                avg_loss=avg_loss,
                expectancy=expectancy,
                risk_reward_ratio=risk_reward,
            )
    except Exception:
        return RiskMetrics(
            sharpe_ratio=None,
            sortino_ratio=None,
            max_drawdown=None,
            max_drawdown_duration_days=None,
            calmar_ratio=None,
            win_rate=None,
            profit_factor=None,
            avg_win=None,
            avg_loss=None,
            expectancy=None,
            risk_reward_ratio=None,
        )


@router.get("/pnl-curve")
async def get_pnl_curve(
    days: int = Query(default=30, ge=1, le=365),
) -> list[PnLCurvePoint]:
    """Get cumulative P&L curve data."""
    try:
        with get_session() as session:
            since = datetime.utcnow() - timedelta(days=days)

            summaries = list(
                session.execute(
                    select(DailySummary)
                    .where(DailySummary.date >= since)
                    .order_by(DailySummary.date)
                )
                .scalars()
                .all()
            )

            cumulative_pnl = 0.0
            results = []
            for s in summaries:
                cumulative_pnl += float(s.total_pnl)
                results.append(
                    PnLCurvePoint(
                        date=s.date.isoformat() if s.date else "",
                        cumulative_pnl=cumulative_pnl,
                        daily_pnl=float(s.total_pnl),
                        trade_count=s.total_trades,
                    )
                )

            return results
    except Exception:
        return []


@router.get("/trade-distribution")
async def get_trade_distribution(
    days: int = Query(default=30, ge=1, le=365),
) -> dict[str, Any]:
    """Get distribution of trade outcomes."""
    try:
        with get_session() as session:
            since = datetime.utcnow() - timedelta(days=days)

            trades = list(
                session.execute(
                    select(Trade)
                    .where(
                        and_(
                            Trade.entry_time >= since,
                            Trade.status == TradeStatus.CLOSED,
                            Trade.pnl.isnot(None),
                        )
                    )
                )
                .scalars()
                .all()
            )

            if not trades:
                return {
                    "pnl_ranges": [],
                    "holding_time_distribution": [],
                    "side_distribution": {"buy": 0, "sell": 0},
                }

            # P&L distribution in buckets
            pnl_values = [float(t.pnl) for t in trades if t.pnl]
            pnl_ranges = [
                {"range": "< -$500", "count": len([p for p in pnl_values if p < -500])},
                {"range": "-$500 to -$100", "count": len([p for p in pnl_values if -500 <= p < -100])},
                {"range": "-$100 to -$50", "count": len([p for p in pnl_values if -100 <= p < -50])},
                {"range": "-$50 to $0", "count": len([p for p in pnl_values if -50 <= p < 0])},
                {"range": "$0 to $50", "count": len([p for p in pnl_values if 0 <= p < 50])},
                {"range": "$50 to $100", "count": len([p for p in pnl_values if 50 <= p < 100])},
                {"range": "$100 to $500", "count": len([p for p in pnl_values if 100 <= p < 500])},
                {"range": "> $500", "count": len([p for p in pnl_values if p >= 500])},
            ]

            # Holding time distribution
            holding_times = [t.holding_time_seconds for t in trades if t.holding_time_seconds]
            holding_dist = [
                {"range": "< 5 min", "count": len([h for h in holding_times if h < 300])},
                {"range": "5-15 min", "count": len([h for h in holding_times if 300 <= h < 900])},
                {"range": "15-30 min", "count": len([h for h in holding_times if 900 <= h < 1800])},
                {"range": "30-60 min", "count": len([h for h in holding_times if 1800 <= h < 3600])},
                {"range": "1-2 hours", "count": len([h for h in holding_times if 3600 <= h < 7200])},
                {"range": "> 2 hours", "count": len([h for h in holding_times if h >= 7200])},
            ]

            # Side distribution
            buy_count = len([t for t in trades if t.side and t.side.value == "buy"])
            sell_count = len([t for t in trades if t.side and t.side.value == "sell"])

            return {
                "pnl_ranges": pnl_ranges,
                "holding_time_distribution": holding_dist,
                "side_distribution": {"buy": buy_count, "sell": sell_count},
            }
    except Exception:
        return {
            "pnl_ranges": [],
            "holding_time_distribution": [],
            "side_distribution": {"buy": 0, "sell": 0},
        }
