"""Database repository layer for data access."""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, desc, func, select
from sqlalchemy.orm import Session

from agent.config.constants import DecisionType, OrderSide, StrategyType, TradeStatus
from agent.database.models import (
    ABTest,
    Alert,
    DailySummary,
    MarketRegimeRecord,
    Strategy,
    StrategyPerformance,
    SystemHealth,
    Trade,
    TradeDecision,
)


class StrategyRepository:
    """Repository for Strategy operations."""

    def __init__(self, session: Session):
        self.session = session

    def get_all(self) -> list[Strategy]:
        """Get all strategies."""
        return list(self.session.execute(select(Strategy)).scalars().all())

    def get_by_name(self, name: str) -> Strategy | None:
        """Get strategy by name."""
        return self.session.execute(
            select(Strategy).where(Strategy.name == name)
        ).scalar_one_or_none()

    def get_by_id(self, strategy_id: UUID) -> Strategy | None:
        """Get strategy by ID."""
        return self.session.get(Strategy, strategy_id)

    def get_active(self) -> list[Strategy]:
        """Get all active strategies."""
        return list(
            self.session.execute(
                select(Strategy).where(Strategy.is_active == True)
            ).scalars().all()
        )

    def create(
        self,
        name: str,
        strategy_type: StrategyType,
        parameters: dict | None = None,
        version: str = "1.0.0",
    ) -> Strategy:
        """Create a new strategy."""
        strategy = Strategy(
            name=name,
            type=strategy_type,
            parameters=parameters or {},
            version=version,
        )
        self.session.add(strategy)
        self.session.flush()
        return strategy

    def update_active_status(
        self, strategy_id: UUID, is_active: bool, reason: str | None = None
    ) -> Strategy | None:
        """Update strategy active status."""
        strategy = self.get_by_id(strategy_id)
        if strategy:
            strategy.is_active = is_active
            if not is_active:
                strategy.disabled_reason = reason
                strategy.disabled_at = datetime.utcnow()
            else:
                strategy.disabled_reason = None
                strategy.disabled_at = None
            self.session.flush()
        return strategy


class TradeRepository:
    """Repository for Trade operations."""

    def __init__(self, session: Session):
        self.session = session

    def get_by_id(self, trade_id: UUID) -> Trade | None:
        """Get trade by ID."""
        return self.session.get(Trade, trade_id)

    def get_open_trades(self) -> list[Trade]:
        """Get all open trades."""
        return list(
            self.session.execute(
                select(Trade).where(Trade.status == TradeStatus.OPEN)
            ).scalars().all()
        )

    def get_trades_by_strategy(
        self,
        strategy_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Trade]:
        """Get trades for a specific strategy."""
        return list(
            self.session.execute(
                select(Trade)
                .where(Trade.strategy_id == strategy_id)
                .order_by(desc(Trade.timestamp))
                .limit(limit)
                .offset(offset)
            ).scalars().all()
        )

    def get_history(
        self,
        limit: int = 100,
        offset: int = 0,
        strategy_name: str | None = None,
        symbol: str | None = None,
        status: TradeStatus | None = None,
    ) -> list[Trade]:
        """Get trade history with optional filters."""
        query = select(Trade).order_by(desc(Trade.timestamp))

        if symbol:
            query = query.where(Trade.symbol == symbol)
        if status:
            query = query.where(Trade.status == status)
        if strategy_name:
            query = query.join(Strategy).where(Strategy.name == strategy_name)

        return list(
            self.session.execute(query.limit(limit).offset(offset)).scalars().all()
        )

    def get_trades_for_date(self, date: datetime) -> list[Trade]:
        """Get all trades for a specific date."""
        start = date.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return list(
            self.session.execute(
                select(Trade).where(
                    and_(Trade.timestamp >= start, Trade.timestamp < end)
                )
            ).scalars().all()
        )

    def get_trade_count(
        self,
        strategy_id: UUID | None = None,
        since: datetime | None = None,
    ) -> int:
        """Get count of trades with optional filters."""
        query = select(func.count(Trade.id))
        if strategy_id:
            query = query.where(Trade.strategy_id == strategy_id)
        if since:
            query = query.where(Trade.timestamp >= since)
        return self.session.execute(query).scalar() or 0

    def create(
        self,
        symbol: str,
        strategy_id: UUID,
        side: OrderSide,
        entry_price: Decimal,
        quantity: Decimal,
        stop_loss: Decimal,
        take_profit: Decimal,
        broker_order_id: str | None = None,
    ) -> Trade:
        """Create a new trade."""
        trade = Trade(
            symbol=symbol,
            strategy_id=strategy_id,
            side=side,
            entry_price=entry_price,
            quantity=quantity,
            stop_loss=stop_loss,
            take_profit=take_profit,
            entry_time=datetime.utcnow(),
            broker_order_id=broker_order_id,
            status=TradeStatus.OPEN,
        )
        self.session.add(trade)
        self.session.flush()
        return trade

    def close_trade(
        self,
        trade_id: UUID,
        exit_price: Decimal,
        pnl: Decimal,
        pnl_percent: Decimal,
    ) -> Trade | None:
        """Close a trade."""
        trade = self.get_by_id(trade_id)
        if trade:
            trade.exit_price = exit_price
            trade.exit_time = datetime.utcnow()
            trade.pnl = pnl
            trade.pnl_percent = pnl_percent
            trade.status = TradeStatus.CLOSED
            if trade.entry_time:
                trade.holding_time_seconds = int(
                    (trade.exit_time - trade.entry_time).total_seconds()
                )
            self.session.flush()
        return trade


class TradeDecisionRepository:
    """Repository for TradeDecision operations."""

    def __init__(self, session: Session):
        self.session = session

    def get_by_trade_id(self, trade_id: UUID) -> list[TradeDecision]:
        """Get all decisions for a trade."""
        return list(
            self.session.execute(
                select(TradeDecision)
                .where(TradeDecision.trade_id == trade_id)
                .order_by(TradeDecision.timestamp)
            ).scalars().all()
        )

    def get_by_strategy(
        self,
        strategy_name: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TradeDecision]:
        """Get decisions for a strategy."""
        return list(
            self.session.execute(
                select(TradeDecision)
                .where(TradeDecision.strategy_name == strategy_name)
                .order_by(desc(TradeDecision.timestamp))
                .limit(limit)
                .offset(offset)
            ).scalars().all()
        )

    def create(
        self,
        decision_type: DecisionType,
        strategy_name: str,
        strategy_version: str,
        symbol: str,
        price: Decimal,
        reasoning_text: str,
        trade_id: UUID | None = None,
        indicators: dict | None = None,
        vix: Decimal | None = None,
        volume: int | None = None,
        trend: str | None = None,
        expected_profit_pct: Decimal | None = None,
        expected_loss_pct: Decimal | None = None,
        confidence_score: Decimal | None = None,
    ) -> TradeDecision:
        """Create a trade decision record."""
        decision = TradeDecision(
            trade_id=trade_id,
            decision_type=decision_type,
            strategy_name=strategy_name,
            strategy_version=strategy_version,
            symbol=symbol,
            price=price,
            reasoning_text=reasoning_text,
            indicators=indicators or {},
            vix=vix,
            volume=volume,
            trend=trend,
            expected_profit_pct=expected_profit_pct,
            expected_loss_pct=expected_loss_pct,
            confidence_score=confidence_score,
        )
        self.session.add(decision)
        self.session.flush()
        return decision

    def update_outcome(
        self,
        decision_id: UUID,
        outcome: str,
        actual_profit_pct: Decimal | None = None,
        what_worked: str | None = None,
        what_failed: str | None = None,
    ) -> TradeDecision | None:
        """Update decision with outcome analysis."""
        decision = self.session.get(TradeDecision, decision_id)
        if decision:
            decision.outcome = outcome
            decision.actual_profit_pct = actual_profit_pct
            decision.what_worked = what_worked
            decision.what_failed = what_failed
            self.session.flush()
        return decision


class StrategyPerformanceRepository:
    """Repository for StrategyPerformance operations."""

    def __init__(self, session: Session):
        self.session = session

    def get_for_date(
        self, strategy_id: UUID, date: datetime
    ) -> StrategyPerformance | None:
        """Get performance record for a strategy on a specific date."""
        date_only = date.replace(hour=0, minute=0, second=0, microsecond=0)
        return self.session.execute(
            select(StrategyPerformance).where(
                and_(
                    StrategyPerformance.strategy_id == strategy_id,
                    StrategyPerformance.date == date_only,
                )
            )
        ).scalar_one_or_none()

    def get_history(
        self,
        strategy_id: UUID,
        days: int = 30,
    ) -> list[StrategyPerformance]:
        """Get performance history for a strategy."""
        since = datetime.utcnow() - timedelta(days=days)
        return list(
            self.session.execute(
                select(StrategyPerformance)
                .where(
                    and_(
                        StrategyPerformance.strategy_id == strategy_id,
                        StrategyPerformance.date >= since,
                    )
                )
                .order_by(desc(StrategyPerformance.date))
            ).scalars().all()
        )

    def get_all_for_date(self, date: datetime) -> list[StrategyPerformance]:
        """Get all strategy performance records for a date."""
        date_only = date.replace(hour=0, minute=0, second=0, microsecond=0)
        return list(
            self.session.execute(
                select(StrategyPerformance).where(
                    StrategyPerformance.date == date_only
                )
            ).scalars().all()
        )

    def upsert(
        self,
        strategy_id: UUID,
        date: datetime,
        **metrics: Any,
    ) -> StrategyPerformance:
        """Create or update performance record."""
        date_only = date.replace(hour=0, minute=0, second=0, microsecond=0)
        record = self.get_for_date(strategy_id, date_only)

        if record:
            for key, value in metrics.items():
                if hasattr(record, key):
                    setattr(record, key, value)
        else:
            record = StrategyPerformance(
                strategy_id=strategy_id,
                date=date_only,
                **metrics,
            )
            self.session.add(record)

        self.session.flush()
        return record


class DailySummaryRepository:
    """Repository for DailySummary operations."""

    def __init__(self, session: Session):
        self.session = session

    def get_for_date(self, date: datetime) -> DailySummary | None:
        """Get summary for a specific date."""
        date_only = date.replace(hour=0, minute=0, second=0, microsecond=0)
        return self.session.execute(
            select(DailySummary).where(DailySummary.date == date_only)
        ).scalar_one_or_none()

    def get_history(self, days: int = 30) -> list[DailySummary]:
        """Get summary history."""
        since = datetime.utcnow() - timedelta(days=days)
        return list(
            self.session.execute(
                select(DailySummary)
                .where(DailySummary.date >= since)
                .order_by(desc(DailySummary.date))
            ).scalars().all()
        )

    def upsert(self, date: datetime, **metrics: Any) -> DailySummary:
        """Create or update daily summary."""
        date_only = date.replace(hour=0, minute=0, second=0, microsecond=0)
        record = self.get_for_date(date_only)

        if record:
            for key, value in metrics.items():
                if hasattr(record, key):
                    setattr(record, key, value)
        else:
            record = DailySummary(date=date_only, **metrics)
            self.session.add(record)

        self.session.flush()
        return record


class AlertRepository:
    """Repository for Alert operations."""

    def __init__(self, session: Session):
        self.session = session

    def get_unread(self, limit: int = 50) -> list[Alert]:
        """Get unread alerts."""
        return list(
            self.session.execute(
                select(Alert)
                .where(Alert.is_read == False)
                .order_by(desc(Alert.timestamp))
                .limit(limit)
            ).scalars().all()
        )

    def get_unresolved(self, limit: int = 50) -> list[Alert]:
        """Get unresolved alerts."""
        return list(
            self.session.execute(
                select(Alert)
                .where(Alert.is_resolved == False)
                .order_by(desc(Alert.timestamp))
                .limit(limit)
            ).scalars().all()
        )

    def create(
        self,
        severity: str,
        alert_type: str,
        message: str,
    ) -> Alert:
        """Create a new alert."""
        from agent.config.constants import AlertSeverity

        alert = Alert(
            severity=AlertSeverity(severity),
            type=alert_type,
            message=message,
        )
        self.session.add(alert)
        self.session.flush()
        return alert

    def mark_read(self, alert_id: UUID) -> Alert | None:
        """Mark an alert as read."""
        alert = self.session.get(Alert, alert_id)
        if alert:
            alert.is_read = True
            self.session.flush()
        return alert

    def resolve(self, alert_id: UUID) -> Alert | None:
        """Resolve an alert."""
        alert = self.session.get(Alert, alert_id)
        if alert:
            alert.is_resolved = True
            alert.resolved_at = datetime.utcnow()
            self.session.flush()
        return alert


class MarketRegimeRepository:
    """Repository for MarketRegimeRecord operations."""

    def __init__(self, session: Session):
        self.session = session

    def get_latest(self, symbol: str) -> MarketRegimeRecord | None:
        """Get latest market regime for a symbol."""
        return self.session.execute(
            select(MarketRegimeRecord)
            .where(MarketRegimeRecord.symbol == symbol)
            .order_by(desc(MarketRegimeRecord.timestamp))
            .limit(1)
        ).scalar_one_or_none()

    def get_history(
        self,
        symbol: str,
        hours: int = 24,
    ) -> list[MarketRegimeRecord]:
        """Get regime history for a symbol."""
        since = datetime.utcnow() - timedelta(hours=hours)
        return list(
            self.session.execute(
                select(MarketRegimeRecord)
                .where(
                    and_(
                        MarketRegimeRecord.symbol == symbol,
                        MarketRegimeRecord.timestamp >= since,
                    )
                )
                .order_by(desc(MarketRegimeRecord.timestamp))
            ).scalars().all()
        )

    def create(
        self,
        symbol: str,
        regime_type: str,
        adx: Decimal | None = None,
        vix: Decimal | None = None,
        volume_ratio: Decimal | None = None,
        trend_strength: Decimal | None = None,
    ) -> MarketRegimeRecord:
        """Record a market regime detection."""
        from agent.config.constants import MarketRegime

        record = MarketRegimeRecord(
            symbol=symbol,
            regime_type=MarketRegime(regime_type),
            adx=adx,
            vix=vix,
            volume_ratio=volume_ratio,
            trend_strength=trend_strength,
        )
        self.session.add(record)
        self.session.flush()
        return record


class SystemHealthRepository:
    """Repository for SystemHealth operations."""

    def __init__(self, session: Session):
        self.session = session

    def get_latest(self) -> SystemHealth | None:
        """Get latest health record."""
        return self.session.execute(
            select(SystemHealth).order_by(desc(SystemHealth.timestamp)).limit(1)
        ).scalar_one_or_none()

    def create(
        self,
        cpu_usage: Decimal | None = None,
        memory_usage: Decimal | None = None,
        active_websockets: int = 0,
        active_strategies: int = 0,
        open_positions: int = 0,
        last_heartbeat: datetime | None = None,
        last_trade: datetime | None = None,
    ) -> SystemHealth:
        """Record system health."""
        record = SystemHealth(
            cpu_usage=cpu_usage,
            memory_usage=memory_usage,
            active_websockets=active_websockets,
            active_strategies=active_strategies,
            open_positions=open_positions,
            last_heartbeat=last_heartbeat,
            last_trade=last_trade,
        )
        self.session.add(record)
        self.session.flush()
        return record
