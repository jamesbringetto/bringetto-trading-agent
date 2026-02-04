"""Metrics collection and calculation."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from loguru import logger


@dataclass
class TradeMetrics:
    """Metrics for a collection of trades."""

    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    breakeven_trades: int = 0

    total_pnl: Decimal = Decimal(0)
    gross_profit: Decimal = Decimal(0)
    gross_loss: Decimal = Decimal(0)

    largest_win: Decimal = Decimal(0)
    largest_loss: Decimal = Decimal(0)

    avg_win: Decimal | None = None
    avg_loss: Decimal | None = None
    avg_trade: Decimal | None = None

    win_rate: float | None = None
    profit_factor: float | None = None

    avg_hold_time_seconds: int | None = None
    total_hold_time_seconds: int = 0

    @property
    def expectancy(self) -> float | None:
        """Calculate trading expectancy."""
        if self.win_rate is None or self.avg_win is None or self.avg_loss is None:
            return None
        return (self.win_rate * float(self.avg_win)) - ((1 - self.win_rate) * abs(float(self.avg_loss)))


@dataclass
class StrategyMetrics:
    """Metrics for a specific strategy."""

    strategy_name: str
    metrics: TradeMetrics = field(default_factory=TradeMetrics)
    consecutive_losses: int = 0
    consecutive_wins: int = 0
    is_active: bool = True
    last_trade_time: datetime | None = None


class MetricsCollector:
    """
    Collects and calculates trading metrics.

    Tracks:
    - Overall performance
    - Per-strategy performance
    - Real-time updates
    """

    def __init__(self):
        self._overall_metrics = TradeMetrics()
        self._strategy_metrics: dict[str, StrategyMetrics] = {}
        self._trade_history: list[dict[str, Any]] = []

    def record_trade(
        self,
        strategy_name: str,
        pnl: Decimal,
        hold_time_seconds: int,
        trade_data: dict[str, Any] | None = None,
    ) -> None:
        """
        Record a completed trade and update metrics.

        Args:
            strategy_name: Name of the strategy
            pnl: Profit/loss from the trade
            hold_time_seconds: How long the position was held
            trade_data: Additional trade data for logging
        """
        # Initialize strategy metrics if needed
        if strategy_name not in self._strategy_metrics:
            self._strategy_metrics[strategy_name] = StrategyMetrics(
                strategy_name=strategy_name
            )

        sm = self._strategy_metrics[strategy_name]
        sm.last_trade_time = datetime.utcnow()

        # Update overall and strategy metrics
        for metrics in [self._overall_metrics, sm.metrics]:
            metrics.total_trades += 1
            metrics.total_pnl += pnl
            metrics.total_hold_time_seconds += hold_time_seconds

            if pnl > 0:
                metrics.winning_trades += 1
                metrics.gross_profit += pnl
                if pnl > metrics.largest_win:
                    metrics.largest_win = pnl
            elif pnl < 0:
                metrics.losing_trades += 1
                metrics.gross_loss += abs(pnl)
                if abs(pnl) > abs(metrics.largest_loss):
                    metrics.largest_loss = pnl
            else:
                metrics.breakeven_trades += 1

        # Update consecutive streaks for strategy
        if pnl > 0:
            sm.consecutive_wins += 1
            sm.consecutive_losses = 0
        elif pnl < 0:
            sm.consecutive_losses += 1
            sm.consecutive_wins = 0

        # Recalculate derived metrics
        self._recalculate_metrics(self._overall_metrics)
        self._recalculate_metrics(sm.metrics)

        # Store trade history
        if trade_data:
            self._trade_history.append({
                **trade_data,
                "strategy": strategy_name,
                "pnl": float(pnl),
                "hold_time_seconds": hold_time_seconds,
                "timestamp": datetime.utcnow().isoformat(),
            })

        logger.info(
            f"Trade recorded - Strategy: {strategy_name}, P&L: ${pnl:.2f}, "
            f"Total P&L: ${self._overall_metrics.total_pnl:.2f}, "
            f"Win rate: {self._overall_metrics.win_rate:.1%}" if self._overall_metrics.win_rate else ""
        )

    def _recalculate_metrics(self, metrics: TradeMetrics) -> None:
        """Recalculate derived metrics."""
        if metrics.total_trades == 0:
            return

        # Win rate
        metrics.win_rate = metrics.winning_trades / metrics.total_trades

        # Average trade
        metrics.avg_trade = metrics.total_pnl / metrics.total_trades

        # Average win/loss
        if metrics.winning_trades > 0:
            metrics.avg_win = metrics.gross_profit / metrics.winning_trades
        if metrics.losing_trades > 0:
            metrics.avg_loss = -metrics.gross_loss / metrics.losing_trades

        # Profit factor
        if metrics.gross_loss > 0:
            metrics.profit_factor = float(metrics.gross_profit / metrics.gross_loss)
        elif metrics.gross_profit > 0:
            metrics.profit_factor = float("inf")

        # Average hold time
        metrics.avg_hold_time_seconds = metrics.total_hold_time_seconds // metrics.total_trades

    def get_overall_metrics(self) -> TradeMetrics:
        """Get overall trading metrics."""
        return self._overall_metrics

    def get_strategy_metrics(self, strategy_name: str) -> StrategyMetrics | None:
        """Get metrics for a specific strategy."""
        return self._strategy_metrics.get(strategy_name)

    def get_all_strategy_metrics(self) -> dict[str, StrategyMetrics]:
        """Get metrics for all strategies."""
        return self._strategy_metrics

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of all metrics."""
        return {
            "overall": {
                "total_trades": self._overall_metrics.total_trades,
                "winning_trades": self._overall_metrics.winning_trades,
                "losing_trades": self._overall_metrics.losing_trades,
                "win_rate": self._overall_metrics.win_rate,
                "total_pnl": float(self._overall_metrics.total_pnl),
                "profit_factor": self._overall_metrics.profit_factor,
                "largest_win": float(self._overall_metrics.largest_win),
                "largest_loss": float(self._overall_metrics.largest_loss),
                "expectancy": self._overall_metrics.expectancy,
            },
            "strategies": {
                name: {
                    "total_trades": sm.metrics.total_trades,
                    "win_rate": sm.metrics.win_rate,
                    "total_pnl": float(sm.metrics.total_pnl),
                    "profit_factor": sm.metrics.profit_factor,
                    "consecutive_losses": sm.consecutive_losses,
                    "consecutive_wins": sm.consecutive_wins,
                    "is_active": sm.is_active,
                }
                for name, sm in self._strategy_metrics.items()
            },
        }

    def should_disable_strategy(
        self, strategy_name: str, max_consecutive_losses: int = 5
    ) -> bool:
        """Check if a strategy should be disabled due to poor performance."""
        sm = self._strategy_metrics.get(strategy_name)
        if not sm:
            return False

        # Check consecutive losses
        if sm.consecutive_losses >= max_consecutive_losses:
            logger.warning(
                f"Strategy {strategy_name} has {sm.consecutive_losses} consecutive losses"
            )
            return True

        # Check minimum trades for statistical significance
        if sm.metrics.total_trades >= 20:
            # Check win rate
            if sm.metrics.win_rate and sm.metrics.win_rate < 0.40:
                logger.warning(
                    f"Strategy {strategy_name} win rate {sm.metrics.win_rate:.1%} below threshold"
                )
                return True

            # Check profit factor
            if sm.metrics.profit_factor and sm.metrics.profit_factor < 0.8:
                logger.warning(
                    f"Strategy {strategy_name} profit factor {sm.metrics.profit_factor:.2f} below threshold"
                )
                return True

        return False

    def reset_strategy_metrics(self, strategy_name: str) -> None:
        """Reset metrics for a strategy (use with caution)."""
        if strategy_name in self._strategy_metrics:
            self._strategy_metrics[strategy_name] = StrategyMetrics(
                strategy_name=strategy_name
            )
            logger.info(f"Metrics reset for strategy: {strategy_name}")

    # -------------------------------------------------------------------------
    # WebSocket Event Recording Methods
    # -------------------------------------------------------------------------

    def record_fill(self, update: dict[str, Any]) -> None:
        """
        Record an order fill event from WebSocket stream.

        Args:
            update: Fill event data from OrderUpdateHandler
        """
        logger.debug(
            f"Recording fill: {update.get('symbol')} - "
            f"Qty: {update.get('filled_qty')} @ ${update.get('filled_avg_price')}"
        )
        # Store in trade history for analysis
        self._trade_history.append({
            "type": "fill",
            "timestamp": datetime.utcnow().isoformat(),
            **update,
        })

    def record_rejection(self, update: dict[str, Any]) -> None:
        """
        Record an order rejection event from WebSocket stream.

        Args:
            update: Rejection event data from OrderUpdateHandler
        """
        logger.warning(
            f"Recording rejection: {update.get('symbol')} - Order {update.get('order_id')}"
        )
        # Store rejection for analysis
        self._trade_history.append({
            "type": "rejection",
            "timestamp": datetime.utcnow().isoformat(),
            **update,
        })

    def record_trade_event(self, event: str, update: dict[str, Any]) -> None:
        """
        Record any trade event from WebSocket stream.

        Args:
            event: Event type (new, fill, canceled, etc.)
            update: Event data from OrderUpdateHandler
        """
        logger.debug(f"Recording trade event: {event} - {update.get('symbol')}")
        # Store all events for comprehensive tracking
        self._trade_history.append({
            "type": event,
            "timestamp": datetime.utcnow().isoformat(),
            **update,
        })
