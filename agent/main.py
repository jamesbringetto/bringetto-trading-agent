"""Main entry point for the Bringetto Trading Agent."""

import asyncio
import signal
import sys
from datetime import datetime

import pytz
from dateutil import parser as date_parser
from loguru import logger

from agent.api.state import set_agent_state
from agent.config.settings import get_settings
from agent.execution.broker import AlpacaBroker
from agent.monitoring.logger import setup_logging
from agent.monitoring.metrics import MetricsCollector
from agent.risk.circuit_breaker import CircuitBreaker
from agent.risk.validator import TradeValidator
from agent.strategies import (
    EODReversal,
    GapAndGo,
    MomentumScalp,
    OpeningRangeBreakout,
    VWAPReversion,
)

# How many seconds before market open to switch to 1-second checks
PRE_MARKET_READY_SECONDS = 5


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

    def _get_seconds_until_market_open(self) -> float | None:
        """
        Calculate seconds until market opens.

        Returns:
            Seconds until market open, or None if unable to determine.
            Returns 0 if market is already open.
        """
        try:
            market_hours = self._broker.get_market_hours()
            if not market_hours:
                return None

            if market_hours.get("is_open"):
                return 0

            next_open_str = market_hours.get("next_open")
            if not next_open_str:
                return None

            # Parse the next_open timestamp
            next_open = date_parser.isoparse(next_open_str)
            now = datetime.now(next_open.tzinfo)

            seconds_until_open = (next_open - now).total_seconds()
            return max(0, seconds_until_open)

        except Exception as e:
            logger.error(f"Error calculating time until market open: {e}")
            return None

    async def _wait_for_market_open(self) -> None:
        """
        Efficiently wait for market to open.

        Uses smart sleeping:
        - If >5 seconds until open: sleep until 5 seconds before
        - If <=5 seconds until open: check every 1 second
        - Checks for shutdown during wait
        """
        while not self._shutdown_event.is_set():
            seconds_until_open = self._get_seconds_until_market_open()

            if seconds_until_open is None:
                # Couldn't determine, fall back to checking every 30 seconds
                logger.warning("Unable to determine market open time, checking in 30s")
                await asyncio.sleep(30)
                continue

            if seconds_until_open == 0:
                # Market is open
                return

            if seconds_until_open <= PRE_MARKET_READY_SECONDS:
                # Within ready window, check every second
                logger.debug(f"Market opens in {seconds_until_open:.1f}s - checking every second")
                await asyncio.sleep(1)
            else:
                # Sleep until ready window, but cap at 5 minutes to allow for shutdown checks
                sleep_time = min(
                    seconds_until_open - PRE_MARKET_READY_SECONDS,
                    300  # Max 5 minute sleep intervals
                )
                hours, remainder = divmod(int(seconds_until_open), 3600)
                minutes, seconds = divmod(remainder, 60)

                if hours > 0:
                    time_str = f"{hours}h {minutes}m {seconds}s"
                elif minutes > 0:
                    time_str = f"{minutes}m {seconds}s"
                else:
                    time_str = f"{seconds}s"

                logger.info(f"Market opens in {time_str} - sleeping for {sleep_time:.0f}s")
                await asyncio.sleep(sleep_time)

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
                    # Wait for market to open (smart waiting)
                    if not self._is_market_open():
                        logger.info("Market is closed - waiting for open...")
                        await self._wait_for_market_open()

                        # Double-check after waiting (in case of shutdown or error)
                        if self._shutdown_event.is_set():
                            break
                        if not self._is_market_open():
                            continue

                    logger.info("Market is OPEN - starting trading loop")

                    # Inner loop while market is open
                    while not self._shutdown_event.is_set() and self._is_market_open():
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

                        # Trading loop runs every second when market is open
                        await asyncio.sleep(1)

                    logger.info("Market is CLOSED - exiting trading loop")

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
