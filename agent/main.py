"""Main entry point for the Bringetto Trading Agent."""

import asyncio
import signal
import sys
from datetime import datetime

import pytz
from loguru import logger

from agent.config.settings import get_settings
from agent.config.constants import TradingConstants
from agent.monitoring.logger import setup_logging
from agent.monitoring.metrics import MetricsCollector
from agent.execution.broker import AlpacaBroker
from agent.risk.circuit_breaker import CircuitBreaker
from agent.risk.validator import TradeValidator
from agent.strategies import (
    OpeningRangeBreakout,
    VWAPReversion,
    MomentumScalp,
    GapAndGo,
    EODReversal,
)
from agent.api.main import set_agent_state


class TradingAgent:
    """
    Main trading agent that orchestrates all components.

    Responsibilities:
    - Initialize and manage strategies
    - Process market data
    - Execute trades
    - Monitor risk
    - Track performance
    """

    def __init__(self):
        self._settings = get_settings()
        self._et_tz = pytz.timezone("America/New_York")

        # Core components
        self._broker = AlpacaBroker()
        self._circuit_breaker = CircuitBreaker(on_trigger=self._on_circuit_breaker_trigger)
        self._validator = TradeValidator()
        self._metrics = MetricsCollector()

        # Strategies
        self._strategies = []
        self._init_strategies()

        # State
        self._is_running = False
        self._shutdown_event = asyncio.Event()

        # Set agent state for API
        set_agent_state("broker", self._broker)
        set_agent_state("circuit_breaker", self._circuit_breaker)
        set_agent_state("strategies", self._strategies)

        logger.info(
            f"TradingAgent initialized - "
            f"Environment: {self._settings.environment}, "
            f"Capital: ${self._settings.paper_trading_capital:,.2f}"
        )

    def _init_strategies(self) -> None:
        """Initialize all trading strategies."""
        settings = self._settings

        if settings.enable_orb:
            self._strategies.append(OpeningRangeBreakout())
            logger.info("Strategy enabled: Opening Range Breakout")

        if settings.enable_vwap_reversion:
            self._strategies.append(VWAPReversion())
            logger.info("Strategy enabled: VWAP Reversion")

        if settings.enable_momentum_scalp:
            self._strategies.append(MomentumScalp())
            logger.info("Strategy enabled: Momentum Scalp")

        if settings.enable_gap_and_go:
            self._strategies.append(GapAndGo())
            logger.info("Strategy enabled: Gap and Go")

        if settings.enable_eod_reversal:
            self._strategies.append(EODReversal())
            logger.info("Strategy enabled: EOD Reversal")

        logger.info(f"Initialized {len(self._strategies)} strategies")

    def _on_circuit_breaker_trigger(self, reason: str) -> None:
        """Callback when circuit breaker is triggered."""
        logger.critical(f"CIRCUIT BREAKER TRIGGERED: {reason}")
        # TODO: Send alerts (Slack, email)
        # TODO: Close all positions if severe

    def _get_market_time(self) -> datetime:
        """Get current time in Eastern timezone."""
        return datetime.now(self._et_tz)

    def _is_market_open(self) -> bool:
        """Check if market is open using broker."""
        return self._broker.is_market_open()

    async def _check_strategies(self) -> None:
        """Check if any strategies should be auto-disabled."""
        for strategy in self._strategies:
            if not strategy.is_active:
                continue

            if self._metrics.should_disable_strategy(strategy.name):
                strategy.disable("Auto-disabled due to poor performance")
                logger.warning(f"Strategy {strategy.name} auto-disabled")

            if self._circuit_breaker.check_strategy_losses(strategy.name):
                strategy.disable("Too many consecutive losses")
                logger.warning(f"Strategy {strategy.name} disabled - consecutive losses")

    async def _daily_reset(self) -> None:
        """Reset daily state for all components."""
        logger.info("Performing daily reset...")

        for strategy in self._strategies:
            if hasattr(strategy, "reset_daily"):
                strategy.reset_daily()

        logger.info("Daily reset complete")

    async def run(self) -> None:
        """Main run loop for the trading agent."""
        logger.info("Starting Trading Agent...")
        self._is_running = True
        set_agent_state("is_running", True)

        # Check account status
        account = self._broker.get_account()
        if account:
            logger.info(
                f"Account status - "
                f"Equity: ${account.equity:,.2f}, "
                f"Cash: ${account.cash:,.2f}, "
                f"Buying power: ${account.buying_power:,.2f}"
            )
        else:
            logger.error("Failed to get account info - check API credentials")
            return

        # Main loop
        try:
            while not self._shutdown_event.is_set():
                try:
                    # Check if market is open
                    if not self._is_market_open():
                        market_hours = self._broker.get_market_hours()
                        if market_hours:
                            logger.debug(f"Market closed. Next open: {market_hours.get('next_open')}")
                        await asyncio.sleep(60)  # Check every minute when closed
                        continue

                    # Check circuit breaker
                    can_trade, reason = self._circuit_breaker.can_trade()
                    if not can_trade:
                        logger.warning(f"Trading paused: {reason}")
                        await asyncio.sleep(60)
                        continue

                    # Check strategies for auto-disable
                    await self._check_strategies()

                    # Process strategies
                    # In a real implementation, this would:
                    # 1. Get market data
                    # 2. Pass to strategies for signal generation
                    # 3. Validate signals
                    # 4. Execute trades
                    # 5. Monitor positions

                    # For now, just a placeholder loop
                    await asyncio.sleep(1)

                except Exception as e:
                    logger.error(f"Error in main loop: {e}")
                    await asyncio.sleep(5)

        except asyncio.CancelledError:
            logger.info("Agent run loop cancelled")
        finally:
            self._is_running = False
            set_agent_state("is_running", False)
            logger.info("Trading Agent stopped")

    async def shutdown(self) -> None:
        """Graceful shutdown of the agent."""
        logger.info("Initiating graceful shutdown...")
        self._shutdown_event.set()

        # Give time for current operations to complete
        await asyncio.sleep(2)

        # Close all positions if configured to do so
        # (disabled by default - manual control preferred)
        # await self._broker.close_all_positions()

        logger.info("Shutdown complete")


def handle_signals(agent: TradingAgent, loop: asyncio.AbstractEventLoop) -> None:
    """Set up signal handlers for graceful shutdown."""

    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}")
        asyncio.run_coroutine_threadsafe(agent.shutdown(), loop)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


async def main() -> None:
    """Main entry point."""
    # Setup logging
    setup_logging()

    logger.info("=" * 60)
    logger.info("BRINGETTO TRADING AGENT")
    logger.info("=" * 60)

    settings = get_settings()
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Trading Mode: {settings.trading_mode}")
    logger.info(f"Paper Trading Capital: ${settings.paper_trading_capital:,.2f}")
    logger.info("=" * 60)

    # Create and run agent
    agent = TradingAgent()

    # Setup signal handlers
    loop = asyncio.get_event_loop()
    handle_signals(agent, loop)

    try:
        await agent.run()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        await agent.shutdown()
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        await agent.shutdown()
        sys.exit(1)


def run() -> None:
    """Synchronous entry point."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
