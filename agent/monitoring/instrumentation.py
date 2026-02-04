"""Instrumentation for trading agent observability.

Provides visibility into:
1. Market data reception - heartbeats showing data is flowing
2. Strategy evaluations - every decision (accepted AND rejected)
3. System health metrics
"""

import asyncio
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
            "timestamp": self.timestamp.isoformat(),
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "evaluation_type": self.evaluation_type,
            "decision": self.decision,
            "rejection_reason": self.rejection_reason,
            "market_context": {
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
            } if self.decision == "accepted" else None,
        }


class Instrumentation:
    """
    Centralized instrumentation for trading agent observability.

    Features:
    - Market data heartbeat logging (periodic confirmation data is flowing)
    - Strategy evaluation tracking (all decisions logged)
    - In-memory stats with periodic summaries
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

        # Data freshness
        bar_age = (now - stats.last_bar_time).total_seconds() if stats.last_bar_time else None
        quote_age = (now - stats.last_quote_time).total_seconds() if stats.last_quote_time else None

        return {
            "runtime_seconds": runtime,
            "totals": {
                "bars": stats.total_bars,
                "quotes": stats.total_quotes,
                "trades": stats.total_trades,
            },
            "rates": {
                "bars_per_second": round(bars_per_second, 2),
                "quotes_per_second": round(quotes_per_second, 2),
            },
            "freshness": {
                "last_bar_age_seconds": round(bar_age, 1) if bar_age else None,
                "last_quote_age_seconds": round(quote_age, 1) if quote_age else None,
                "is_receiving_data": bar_age is not None and bar_age < 120,
            },
            "symbols_with_bars": len(stats.bars_per_symbol),
            "symbols_with_quotes": len(stats.quotes_per_symbol),
            "top_symbols_by_bars": dict(
                sorted(
                    stats.bars_per_symbol.items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:10]
            ),
        }

    def log_heartbeat(self) -> None:
        """Log a heartbeat showing data reception status."""
        stats = self.get_data_stats()
        freshness = stats["freshness"]

        if freshness["is_receiving_data"]:
            logger.info(
                f"[HEARTBEAT] Data flowing - "
                f"Bars: {stats['totals']['bars']} ({stats['rates']['bars_per_second']}/s), "
                f"Quotes: {stats['totals']['quotes']} ({stats['rates']['quotes_per_second']}/s), "
                f"Symbols: {stats['symbols_with_bars']} bars, {stats['symbols_with_quotes']} quotes, "
                f"Last bar: {freshness['last_bar_age_seconds']}s ago"
            )
        else:
            logger.warning(
                f"[HEARTBEAT] NO DATA RECEIVED - "
                f"Last bar: {freshness['last_bar_age_seconds']}s ago" if freshness['last_bar_age_seconds'] else "Never"
            )

        self._last_heartbeat = datetime.utcnow()

    async def start_heartbeat(self) -> None:
        """Start the periodic heartbeat logging."""
        logger.info(f"Starting heartbeat every {self._heartbeat_interval}s")

        async def heartbeat_loop():
            while True:
                await asyncio.sleep(self._heartbeat_interval)
                self.log_heartbeat()

        self._heartbeat_task = asyncio.create_task(heartbeat_loop())

    async def stop_heartbeat(self) -> None:
        """Stop the heartbeat logging."""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
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

        # Store in memory (with limit)
        self._evaluations.append(evaluation)
        if len(self._evaluations) > self._max_evaluations:
            self._evaluations = self._evaluations[-self._max_evaluations:]

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
        Get summary of evaluations in the last N minutes.

        Args:
            minutes: Time window in minutes

        Returns:
            Summary statistics
        """
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        recent = [e for e in self._evaluations if e.timestamp >= cutoff]

        by_strategy: dict[str, dict[str, int]] = defaultdict(lambda: {"accepted": 0, "rejected": 0, "skipped": 0})
        by_symbol: dict[str, int] = defaultdict(int)

        for e in recent:
            by_strategy[e.strategy_name][e.decision] += 1
            by_symbol[e.symbol] += 1

        total_accepted = sum(1 for e in recent if e.decision == "accepted")
        total_rejected = sum(1 for e in recent if e.decision == "rejected")
        total = len(recent)

        return {
            "time_window_minutes": minutes,
            "total_evaluations": total,
            "accepted": total_accepted,
            "rejected": total_rejected,
            "acceptance_rate": round(total_accepted / total * 100, 1) if total > 0 else 0,
            "by_strategy": dict(by_strategy),
            "top_symbols_evaluated": dict(
                sorted(by_symbol.items(), key=lambda x: x[1], reverse=True)[:10]
            ),
        }

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
