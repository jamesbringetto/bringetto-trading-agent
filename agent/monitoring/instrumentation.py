"""Instrumentation for trading agent observability.

Provides visibility into:
1. Market data reception - heartbeats showing data is flowing
2. Strategy evaluations - every decision (accepted AND rejected)
3. System health metrics

Counter data is periodically persisted to PostgreSQL so that metrics
survive agent redeployments and support historical time-range queries.
"""

import asyncio
import contextlib
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from loguru import logger


@dataclass
class DataReceptionStats:
    """Statistics for market data reception."""

    total_bars: int = 0
    total_quotes: int = 0
    total_trades: int = 0
    bars_per_symbol: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    quotes_per_symbol: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    last_bar_time: datetime | None = None
    last_quote_time: datetime | None = None
    last_trade_time: datetime | None = None
    start_time: datetime = field(default_factory=datetime.utcnow)


@dataclass
class StrategyEvaluation:
    """Record of a strategy evaluation - whether accepted or rejected."""

    id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    strategy_name: str = ""
    symbol: str = ""
    evaluation_type: str = "entry"  # 'entry' or 'exit'

    # Decision
    decision: str = "rejected"  # 'accepted', 'rejected', 'skipped'
    rejection_reason: str | None = None

    # Market context at evaluation time
    current_price: Decimal | None = None
    volume: int | None = None
    vwap: Decimal | None = None
    rsi: float | None = None
    macd: float | None = None
    atr: float | None = None
    vix: float | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None

    # Signal details (if accepted)
    signal_side: str | None = None
    signal_confidence: float | None = None
    signal_reasoning: str | None = None
    entry_price: Decimal | None = None
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging/storage."""
        return {
            "id": str(self.id),
            "timestamp": self.timestamp.isoformat() + "Z",  # Append Z to indicate UTC
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "evaluation_type": self.evaluation_type,
            "decision": self.decision,
            "rejection_reason": self.rejection_reason,
            "context": {
                "current_price": str(self.current_price) if self.current_price else None,
                "volume": self.volume,
                "vwap": str(self.vwap) if self.vwap else None,
                "rsi": self.rsi,
                "macd": self.macd,
                "atr": self.atr,
                "vix": self.vix,
                "bid": str(self.bid) if self.bid else None,
                "ask": str(self.ask) if self.ask else None,
            },
            "signal": {
                "side": self.signal_side,
                "confidence": self.signal_confidence,
                "reasoning": self.signal_reasoning,
                "entry_price": str(self.entry_price) if self.entry_price else None,
                "stop_loss": str(self.stop_loss) if self.stop_loss else None,
                "take_profit": str(self.take_profit) if self.take_profit else None,
            }
            if self.decision == "accepted"
            else None,
        }


def _default_funnel() -> dict[str, int]:
    """Return the default funnel counter structure."""
    return {
        "skipped_no_data": 0,
        "signal_generated": 0,
        "blocked_pdt": 0,
        "blocked_risk_validation": 0,
        "blocked_position_size": 0,
        "orders_submitted": 0,
        "orders_failed": 0,
        "orders_filled": 0,
        "trades_closed": 0,
        "trades_won": 0,
        "trades_lost": 0,
    }


def _default_risk_breakdown() -> dict[str, int]:
    """Return the default risk rejection breakdown structure."""
    return {
        "market_hours": 0,
        "no_stop_loss": 0,
        "invalid_stop_loss": 0,
        "position_size": 0,
        "buying_power": 0,
        "daytrading_buying_power": 0,
        "max_positions": 0,
        "max_exposure": 0,
        "min_price": 0,
    }


def _default_strategy_funnel() -> dict[str, int]:
    """Return the default per-strategy funnel counter structure."""
    return {
        "signal_generated": 0,
        "blocked_pdt": 0,
        "blocked_risk_validation": 0,
        "blocked_position_size": 0,
        "orders_submitted": 0,
        "orders_failed": 0,
        "orders_filled": 0,
        "trades_closed": 0,
        "trades_won": 0,
        "trades_lost": 0,
    }


class Instrumentation:
    """
    Centralized instrumentation for trading agent observability.

    Features:
    - Market data heartbeat logging (periodic confirmation data is flowing)
    - Strategy evaluation tracking (all decisions logged)
    - In-memory stats with periodic summaries
    - Periodic persistence to PostgreSQL for surviving redeployments
    """

    def __init__(
        self,
        heartbeat_interval_seconds: int = 60,
        max_evaluations_in_memory: int = 1000,
    ):
        self._heartbeat_interval = heartbeat_interval_seconds
        self._max_evaluations = max_evaluations_in_memory
        self._data_stats = DataReceptionStats()
        self._evaluations: list[StrategyEvaluation] = []
        self._last_heartbeat: datetime | None = None
        self._heartbeat_task: asyncio.Task | None = None

        # Cumulative counters (not capped like the evaluations list)
        self._total_evaluations: int = 0
        self._total_accepted: int = 0
        self._total_rejected: int = 0
        self._total_skipped: int = 0
        self._by_strategy_cumulative: dict[str, dict[str, int]] = defaultdict(
            lambda: {"total": 0, "accepted": 0, "rejected": 0}
        )

        # Funnel counters (aggregate)
        self._funnel: dict[str, int] = _default_funnel()

        # Risk rejection breakdown (aggregate)
        self._risk_rejection_breakdown: dict[str, int] = _default_risk_breakdown()

        # Per-strategy funnel counters
        self._by_strategy_funnel: dict[str, dict[str, int]] = defaultdict(
            lambda: _default_strategy_funnel()
        )

        # Per-strategy risk rejection breakdown
        self._by_strategy_risk_breakdown: dict[str, dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )

        # ---- Snapshot persistence tracking ----
        # Track what was last persisted so we can compute deltas
        self._last_snapshot_time: datetime = datetime.utcnow()
        self._last_snapshot_bars: int = 0
        self._last_snapshot_quotes: int = 0
        self._last_snapshot_trades: int = 0
        self._last_snapshot_evaluations: int = 0
        self._last_snapshot_accepted: int = 0
        self._last_snapshot_rejected: int = 0
        self._last_snapshot_skipped: int = 0
        self._last_snapshot_funnel: dict[str, int] = _default_funnel()
        self._last_snapshot_risk_breakdown: dict[str, int] = _default_risk_breakdown()
        self._last_snapshot_by_strategy_cumulative: dict[str, dict[str, int]] = {}
        self._last_snapshot_by_strategy_funnel: dict[str, dict[str, int]] = {}
        self._last_snapshot_by_strategy_risk: dict[str, dict[str, int]] = {}

        logger.info(
            f"Instrumentation initialized - "
            f"heartbeat every {heartbeat_interval_seconds}s, "
            f"max {max_evaluations_in_memory} evaluations in memory"
        )

    # -------------------------------------------------------------------------
    # Market Data Reception Tracking
    # -------------------------------------------------------------------------

    def record_bar(self, symbol: str) -> None:
        """Record reception of a bar (OHLCV) data point."""
        self._data_stats.total_bars += 1
        self._data_stats.bars_per_symbol[symbol] += 1
        self._data_stats.last_bar_time = datetime.utcnow()

    def record_quote(self, symbol: str) -> None:
        """Record reception of a quote (bid/ask) data point."""
        self._data_stats.total_quotes += 1
        self._data_stats.quotes_per_symbol[symbol] += 1
        self._data_stats.last_quote_time = datetime.utcnow()

    def record_trade_tick(self, symbol: str) -> None:
        """Record reception of a trade tick."""
        self._data_stats.total_trades += 1
        self._data_stats.last_trade_time = datetime.utcnow()

    def get_data_stats(self) -> dict[str, Any]:
        """Get current data reception statistics."""
        stats = self._data_stats
        now = datetime.utcnow()
        runtime = (now - stats.start_time).total_seconds()

        # Calculate rates
        bars_per_second = stats.total_bars / runtime if runtime > 0 else 0
        quotes_per_second = stats.total_quotes / runtime if runtime > 0 else 0
        trades_per_second = stats.total_trades / runtime if runtime > 0 else 0

        # Data freshness - use the most recent data time
        last_times = [
            t for t in [stats.last_bar_time, stats.last_quote_time, stats.last_trade_time] if t
        ]
        last_data_time = max(last_times) if last_times else None
        first_data_time = stats.start_time
        data_freshness = (now - last_data_time).total_seconds() if last_data_time else None

        return {
            "total_bars": stats.total_bars,
            "total_quotes": stats.total_quotes,
            "total_trades": stats.total_trades,
            "unique_symbols_bars": len(stats.bars_per_symbol),
            "unique_symbols_quotes": len(stats.quotes_per_symbol),
            "unique_symbols_trades": 0,  # Not tracked per symbol currently
            "first_data_time": first_data_time.isoformat() + "Z" if first_data_time else None,
            "last_data_time": last_data_time.isoformat() + "Z" if last_data_time else None,
            "data_freshness_seconds": round(data_freshness, 1) if data_freshness else None,
            "bars_per_second": round(bars_per_second, 2),
            "quotes_per_second": round(quotes_per_second, 2),
            "trades_per_second": round(trades_per_second, 2),
        }

    def log_heartbeat(self) -> None:
        """Log a heartbeat showing data reception status."""
        stats = self.get_data_stats()
        is_receiving = (
            stats["data_freshness_seconds"] is not None and stats["data_freshness_seconds"] < 120
        )

        if is_receiving:
            logger.info(
                f"[HEARTBEAT] Data flowing - "
                f"Bars: {stats['total_bars']} ({stats['bars_per_second']}/s), "
                f"Quotes: {stats['total_quotes']} ({stats['quotes_per_second']}/s), "
                f"Symbols: {stats['unique_symbols_bars']} bars, {stats['unique_symbols_quotes']} quotes, "
                f"Last data: {stats['data_freshness_seconds']}s ago"
            )
        else:
            freshness = stats["data_freshness_seconds"]
            logger.warning(
                f"[HEARTBEAT] NO DATA RECEIVED - Last data: {freshness}s ago"
                if freshness
                else "Never"
            )

        self._last_heartbeat = datetime.utcnow()

    async def start_heartbeat(self) -> None:
        """Start the periodic heartbeat logging."""
        logger.info(f"Starting heartbeat every {self._heartbeat_interval}s")

        async def heartbeat_loop():
            while True:
                await asyncio.sleep(self._heartbeat_interval)
                self.log_heartbeat()
                # Persist snapshot to DB on each heartbeat
                self.save_snapshot()

        self._heartbeat_task = asyncio.create_task(heartbeat_loop())

    async def stop_heartbeat(self) -> None:
        """Stop the heartbeat logging."""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat_task
            # Persist final snapshot before stopping
            self.save_snapshot()
            logger.info("Heartbeat stopped")

    # -------------------------------------------------------------------------
    # Strategy Evaluation Tracking
    # -------------------------------------------------------------------------

    def record_evaluation(
        self,
        strategy_name: str,
        symbol: str,
        evaluation_type: str,
        decision: str,
        context: dict[str, Any] | None = None,
        rejection_reason: str | None = None,
        signal: dict[str, Any] | None = None,
    ) -> StrategyEvaluation:
        """
        Record a strategy evaluation (entry or exit decision).

        Args:
            strategy_name: Name of the strategy
            symbol: Symbol being evaluated
            evaluation_type: 'entry' or 'exit'
            decision: 'accepted', 'rejected', or 'skipped'
            context: Market context at evaluation time
            rejection_reason: Why the signal was rejected (if rejected)
            signal: Signal details (if accepted)

        Returns:
            The recorded evaluation
        """
        evaluation = StrategyEvaluation(
            strategy_name=strategy_name,
            symbol=symbol,
            evaluation_type=evaluation_type,
            decision=decision,
            rejection_reason=rejection_reason,
        )

        # Populate market context
        if context:
            evaluation.current_price = context.get("current_price")
            evaluation.volume = context.get("volume")
            evaluation.vwap = context.get("vwap")
            evaluation.rsi = context.get("rsi")
            evaluation.macd = context.get("macd")
            evaluation.atr = context.get("atr")
            evaluation.vix = context.get("vix")
            evaluation.bid = context.get("bid")
            evaluation.ask = context.get("ask")

        # Populate signal details if accepted
        if signal and decision == "accepted":
            evaluation.signal_side = signal.get("side")
            evaluation.signal_confidence = signal.get("confidence")
            evaluation.signal_reasoning = signal.get("reasoning")
            evaluation.entry_price = signal.get("entry_price")
            evaluation.stop_loss = signal.get("stop_loss")
            evaluation.take_profit = signal.get("take_profit")

        # Store in memory (with limit for recent evaluations display)
        self._evaluations.append(evaluation)
        if len(self._evaluations) > self._max_evaluations:
            self._evaluations = self._evaluations[-self._max_evaluations :]

        # Update cumulative counters (unlimited)
        self._total_evaluations += 1
        self._by_strategy_cumulative[strategy_name]["total"] += 1
        if decision == "accepted":
            self._total_accepted += 1
            self._by_strategy_cumulative[strategy_name]["accepted"] += 1
        elif decision == "rejected":
            self._total_rejected += 1
            self._by_strategy_cumulative[strategy_name]["rejected"] += 1
        elif decision == "skipped":
            self._total_skipped += 1

        # Log based on decision type
        if decision == "accepted":
            logger.info(
                f"[EVAL] {strategy_name} | {symbol} | {evaluation_type.upper()} ACCEPTED | "
                f"Side: {evaluation.signal_side}, "
                f"Confidence: {evaluation.signal_confidence:.0%}, "
                f"Price: ${evaluation.current_price}"
            )
        else:
            logger.debug(
                f"[EVAL] {strategy_name} | {symbol} | {evaluation_type.upper()} {decision.upper()} | "
                f"Reason: {rejection_reason or 'No signal'}"
            )

        return evaluation

    def record_rejection_batch(
        self,
        strategy_name: str,
        count: int,
    ) -> None:
        """
        Record a batch of rejected evaluations (counter-only, no individual records).

        Use this for high-volume "no signal" rejections to avoid flooding the
        evaluations list with thousands of entries per loop cycle.

        Args:
            strategy_name: Name of the strategy
            count: Number of rejected evaluations
        """
        self._total_evaluations += count
        self._total_rejected += count
        self._by_strategy_cumulative[strategy_name]["total"] += count
        self._by_strategy_cumulative[strategy_name]["rejected"] += count

    def record_pipeline_event(
        self,
        stage: str,
        strategy_name: str | None = None,
        failure_code: str | None = None,
    ) -> None:
        """
        Record a funnel pipeline event.

        Args:
            stage: The pipeline stage. Valid values:
                - "skipped_no_data": Market context unavailable (aggregate only)
                - "signal_generated": Strategy generated a signal
                - "blocked_pdt": PDT rule prevented entry
                - "blocked_risk_validation": Risk validation failed
                - "blocked_position_size": Position size < 1 share
                - "orders_submitted": Order submitted to broker
                - "orders_failed": Order submission failed
                - "orders_filled": Order filled (entry)
                - "trades_closed": Trade closed (exit)
                - "trades_won": Trade closed with profit
                - "trades_lost": Trade closed with loss
            strategy_name: Name of the strategy (None for aggregate-only events)
            failure_code: For "blocked_risk_validation", the specific risk check that failed
        """
        # Update aggregate funnel counter
        if stage in self._funnel:
            self._funnel[stage] += 1

        # Update per-strategy funnel counter (if strategy provided)
        if strategy_name and stage != "skipped_no_data":
            # Ensure the strategy entry exists with all keys
            if strategy_name not in self._by_strategy_funnel:
                self._by_strategy_funnel[strategy_name] = _default_strategy_funnel()
            if stage in self._by_strategy_funnel[strategy_name]:
                self._by_strategy_funnel[strategy_name][stage] += 1

        # Update risk rejection breakdown
        if stage == "blocked_risk_validation" and failure_code:
            if failure_code in self._risk_rejection_breakdown:
                self._risk_rejection_breakdown[failure_code] += 1

            # Per-strategy risk breakdown
            if strategy_name:
                self._by_strategy_risk_breakdown[strategy_name][failure_code] += 1

        # Log significant events
        if stage in ("orders_submitted", "orders_filled", "trades_won", "trades_lost"):
            logger.debug(f"[FUNNEL] {stage} | Strategy: {strategy_name or 'N/A'}")

    def get_evaluations(
        self,
        strategy_name: str | None = None,
        symbol: str | None = None,
        decision: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """
        Get recent evaluations with optional filters.

        Args:
            strategy_name: Filter by strategy
            symbol: Filter by symbol
            decision: Filter by decision ('accepted', 'rejected', 'skipped')
            since: Only evaluations after this time
            limit: Maximum number to return

        Returns:
            List of evaluation dictionaries
        """
        results = []
        for eval in reversed(self._evaluations):
            if strategy_name and eval.strategy_name != strategy_name:
                continue
            if symbol and eval.symbol != symbol:
                continue
            if decision and eval.decision != decision:
                continue
            if since and eval.timestamp < since:
                continue

            results.append(eval.to_dict())
            if len(results) >= limit:
                break

        return results

    def get_evaluation_summary(self, minutes: int = 60) -> dict[str, Any]:
        """
        Get summary of evaluations.

        Uses cumulative counters for total counts (unlimited), and recent
        evaluations list for time-windowed metrics like acceptance rate.

        Args:
            minutes: Time window in minutes (for acceptance rate calculation)

        Returns:
            Summary statistics with cumulative totals
        """
        # Calculate acceptance rate from recent evaluations within time window
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        recent = [e for e in self._evaluations if e.timestamp >= cutoff]

        by_symbol: dict[str, int] = defaultdict(int)
        for e in recent:
            by_symbol[e.symbol] += 1

        recent_accepted = sum(1 for e in recent if e.decision == "accepted")
        recent_total = len(recent)

        # Build per-strategy data with funnel and risk breakdown
        by_strategy_full: dict[str, dict[str, Any]] = {}
        for strategy_name, basic_stats in self._by_strategy_cumulative.items():
            by_strategy_full[strategy_name] = {
                **dict(basic_stats),  # total, accepted, rejected
                "funnel": dict(self._by_strategy_funnel.get(strategy_name, {})),
                "risk_rejection_breakdown": dict(
                    self._by_strategy_risk_breakdown.get(strategy_name, {})
                ),
            }

        return {
            "time_window_minutes": minutes,
            # Use cumulative counters for totals (unlimited)
            "total_evaluations": self._total_evaluations,
            "accepted": self._total_accepted,
            "rejected": self._total_rejected,
            "skipped": self._total_skipped,
            # Acceptance rate based on recent window
            "acceptance_rate": round(recent_accepted / recent_total, 4) if recent_total > 0 else 0,
            # Use cumulative strategy counters with funnel data
            "by_strategy": by_strategy_full,
            "by_symbol": dict(by_symbol),
            # Aggregate funnel data
            "funnel": dict(self._funnel),
            "risk_rejection_breakdown": dict(self._risk_rejection_breakdown),
        }

    # -------------------------------------------------------------------------
    # Snapshot Persistence
    # -------------------------------------------------------------------------

    def _compute_snapshot_delta(self) -> dict[str, Any]:
        """Compute the delta between current counters and last persisted snapshot."""
        now = datetime.utcnow()

        # Data reception deltas
        bars_delta = self._data_stats.total_bars - self._last_snapshot_bars
        quotes_delta = self._data_stats.total_quotes - self._last_snapshot_quotes
        trades_delta = self._data_stats.total_trades - self._last_snapshot_trades

        # Evaluation count deltas
        evals_delta = self._total_evaluations - self._last_snapshot_evaluations
        accepted_delta = self._total_accepted - self._last_snapshot_accepted
        rejected_delta = self._total_rejected - self._last_snapshot_rejected
        skipped_delta = self._total_skipped - self._last_snapshot_skipped

        # Funnel deltas
        funnel_delta = {}
        for key in self._funnel:
            delta = self._funnel[key] - self._last_snapshot_funnel.get(key, 0)
            if delta != 0:
                funnel_delta[key] = delta

        # Risk breakdown deltas
        risk_delta = {}
        for key in self._risk_rejection_breakdown:
            delta = self._risk_rejection_breakdown[key] - self._last_snapshot_risk_breakdown.get(
                key, 0
            )
            if delta != 0:
                risk_delta[key] = delta

        # Per-strategy deltas
        by_strategy_delta: dict[str, dict[str, Any]] = {}
        for strategy_name in set(
            list(self._by_strategy_cumulative.keys())
            + list(self._by_strategy_funnel.keys())
            + list(self._by_strategy_risk_breakdown.keys())
        ):
            strategy_delta: dict[str, Any] = {}

            # Cumulative eval counts
            if strategy_name in self._by_strategy_cumulative:
                for key, val in self._by_strategy_cumulative[strategy_name].items():
                    prev = self._last_snapshot_by_strategy_cumulative.get(strategy_name, {}).get(
                        key, 0
                    )
                    d = val - prev
                    if d != 0:
                        strategy_delta[key] = d

            # Funnel
            if strategy_name in self._by_strategy_funnel:
                funnel_d: dict[str, int] = {}
                for key, val in self._by_strategy_funnel[strategy_name].items():
                    prev = self._last_snapshot_by_strategy_funnel.get(strategy_name, {}).get(key, 0)
                    d = val - prev
                    if d != 0:
                        funnel_d[key] = d
                if funnel_d:
                    strategy_delta["funnel"] = funnel_d

            # Risk breakdown
            if strategy_name in self._by_strategy_risk_breakdown:
                risk_d: dict[str, int] = {}
                for key, val in self._by_strategy_risk_breakdown[strategy_name].items():
                    prev = self._last_snapshot_by_strategy_risk.get(strategy_name, {}).get(key, 0)
                    d = val - prev
                    if d != 0:
                        risk_d[key] = d
                if risk_d:
                    strategy_delta["risk_rejection_breakdown"] = risk_d

            if strategy_delta:
                by_strategy_delta[strategy_name] = strategy_delta

        return {
            "period_start": self._last_snapshot_time,
            "period_end": now,
            "bars_received": bars_delta,
            "quotes_received": quotes_delta,
            "trades_received": trades_delta,
            "total_evaluations": evals_delta,
            "accepted": accepted_delta,
            "rejected": rejected_delta,
            "skipped": skipped_delta,
            "funnel": funnel_delta,
            "risk_rejection_breakdown": risk_delta,
            "by_strategy": by_strategy_delta,
        }

    def _update_last_snapshot_markers(self) -> None:
        """Update the 'last persisted' markers to current counter values."""
        self._last_snapshot_time = datetime.utcnow()
        self._last_snapshot_bars = self._data_stats.total_bars
        self._last_snapshot_quotes = self._data_stats.total_quotes
        self._last_snapshot_trades = self._data_stats.total_trades
        self._last_snapshot_evaluations = self._total_evaluations
        self._last_snapshot_accepted = self._total_accepted
        self._last_snapshot_rejected = self._total_rejected
        self._last_snapshot_skipped = self._total_skipped
        self._last_snapshot_funnel = dict(self._funnel)
        self._last_snapshot_risk_breakdown = dict(self._risk_rejection_breakdown)

        # Deep copy per-strategy data
        self._last_snapshot_by_strategy_cumulative = {
            k: dict(v) for k, v in self._by_strategy_cumulative.items()
        }
        self._last_snapshot_by_strategy_funnel = {
            k: dict(v) for k, v in self._by_strategy_funnel.items()
        }
        self._last_snapshot_by_strategy_risk = {
            k: dict(v) for k, v in self._by_strategy_risk_breakdown.items()
        }

    def save_snapshot(self) -> bool:
        """Persist a delta snapshot of current counters to the database.

        Computes the difference between current counter values and the
        values at the time of the last snapshot, then writes that delta
        to the instrumentation_snapshots table.

        Returns True if snapshot was saved, False on error.
        """
        try:
            from agent.database import get_session
            from agent.database.repositories import InstrumentationSnapshotRepository

            delta = self._compute_snapshot_delta()

            # Skip if there's nothing to persist
            has_data = (
                delta["bars_received"] > 0
                or delta["quotes_received"] > 0
                or delta["trades_received"] > 0
                or delta["total_evaluations"] > 0
                or delta["funnel"]
                or delta["risk_rejection_breakdown"]
                or delta["by_strategy"]
            )
            if not has_data:
                return True

            with get_session() as session:
                repo = InstrumentationSnapshotRepository(session)
                repo.create(
                    period_start=delta["period_start"],
                    period_end=delta["period_end"],
                    bars_received=delta["bars_received"],
                    quotes_received=delta["quotes_received"],
                    trades_received=delta["trades_received"],
                    total_evaluations=delta["total_evaluations"],
                    accepted=delta["accepted"],
                    rejected=delta["rejected"],
                    skipped=delta["skipped"],
                    funnel=delta["funnel"],
                    risk_rejection_breakdown=delta["risk_rejection_breakdown"],
                    by_strategy=delta["by_strategy"],
                )

            self._update_last_snapshot_markers()
            logger.debug(
                f"[SNAPSHOT] Persisted instrumentation delta - "
                f"evals={delta['total_evaluations']}, "
                f"bars={delta['bars_received']}, "
                f"quotes={delta['quotes_received']}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to persist instrumentation snapshot: {e}")
            return False

    def get_historical_summary(self, since: datetime) -> dict[str, Any]:
        """Query DB for aggregated counters since the given time,
        plus any unsaved delta from the current session.

        Args:
            since: Start of the time window

        Returns:
            Combined summary dict with DB history + current unsaved delta
        """
        try:
            from agent.database import get_session
            from agent.database.repositories import InstrumentationSnapshotRepository

            with get_session() as session:
                repo = InstrumentationSnapshotRepository(session)
                db_totals = repo.get_aggregated_since(since)
        except Exception as e:
            logger.error(f"Failed to query historical snapshots: {e}")
            db_totals = {
                "bars_received": 0,
                "quotes_received": 0,
                "trades_received": 0,
                "total_evaluations": 0,
                "accepted": 0,
                "rejected": 0,
                "skipped": 0,
                "funnel": {},
                "risk_rejection_breakdown": {},
                "by_strategy": {},
            }

        # Add current unsaved delta (changes since last snapshot)
        unsaved = self._compute_snapshot_delta()

        result = {
            "total_evaluations": db_totals["total_evaluations"] + unsaved["total_evaluations"],
            "accepted": db_totals["accepted"] + unsaved["accepted"],
            "rejected": db_totals["rejected"] + unsaved["rejected"],
            "skipped": db_totals["skipped"] + unsaved["skipped"],
            "bars_received": db_totals["bars_received"] + unsaved["bars_received"],
            "quotes_received": db_totals["quotes_received"] + unsaved["quotes_received"],
            "trades_received": db_totals["trades_received"] + unsaved["trades_received"],
        }

        # Merge funnel (start with all default keys at 0)
        funnel = _default_funnel()
        for key, val in db_totals.get("funnel", {}).items():
            funnel[key] = funnel.get(key, 0) + val
        for key, val in unsaved.get("funnel", {}).items():
            funnel[key] = funnel.get(key, 0) + val
        result["funnel"] = funnel

        # Merge risk breakdown (start with all default keys at 0)
        risk = _default_risk_breakdown()
        for key, val in db_totals.get("risk_rejection_breakdown", {}).items():
            risk[key] = risk.get(key, 0) + val
        for key, val in unsaved.get("risk_rejection_breakdown", {}).items():
            risk[key] = risk.get(key, 0) + val
        result["risk_rejection_breakdown"] = risk

        # Merge by_strategy
        by_strategy: dict[str, dict[str, Any]] = {}
        for src in [db_totals.get("by_strategy", {}), unsaved.get("by_strategy", {})]:
            for strategy_name, strategy_data in src.items():
                if strategy_name not in by_strategy:
                    by_strategy[strategy_name] = {}
                for key, val in strategy_data.items():
                    if isinstance(val, dict):
                        if key not in by_strategy[strategy_name]:
                            by_strategy[strategy_name][key] = {}
                        for k2, v2 in val.items():
                            by_strategy[strategy_name][key][k2] = (
                                by_strategy[strategy_name][key].get(k2, 0) + v2
                            )
                    else:
                        by_strategy[strategy_name][key] = (
                            by_strategy[strategy_name].get(key, 0) + val
                        )
        result["by_strategy"] = by_strategy

        # Acceptance rate from the combined totals
        total = result["total_evaluations"]
        accepted = result["accepted"]
        result["acceptance_rate"] = round(accepted / total, 4) if total > 0 else 0

        return result

    # -------------------------------------------------------------------------
    # Full Status
    # -------------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Get complete instrumentation status."""
        return {
            "data_reception": self.get_data_stats(),
            "evaluations": self.get_evaluation_summary(minutes=60),
            "recent_accepted_signals": self.get_evaluations(decision="accepted", limit=10),
        }


# Global instrumentation instance
_instrumentation: Instrumentation | None = None


def get_instrumentation() -> Instrumentation:
    """Get the global instrumentation instance."""
    global _instrumentation
    if _instrumentation is None:
        _instrumentation = Instrumentation()
    return _instrumentation


def set_instrumentation(inst: Instrumentation) -> None:
    """Set the global instrumentation instance."""
    global _instrumentation
    _instrumentation = inst
