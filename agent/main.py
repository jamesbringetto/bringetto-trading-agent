"""Main entry point for the Bringetto Trading Agent.

24/5 Trading Support:
- Paper trading runs from Sunday 8 PM ET through Friday 8 PM ET continuously
- Trading sessions: Overnight (8PM-4AM), Pre-market (4AM-9:30AM),
  Regular (9:30AM-4PM), After-hours (4PM-8PM)
- Weekend closure: Friday 8 PM ET through Sunday 8 PM ET
"""

import asyncio
import signal
import sys
from datetime import datetime, timedelta

import pytz
from dateutil import parser as date_parser
from loguru import logger

from agent.api.state import set_agent_state
from agent.config.constants import TradingSession
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

# Weekend closure times (in Eastern Time)
# Trading closes Friday 8 PM ET and reopens Sunday 8 PM ET
WEEKEND_CLOSE_DAY = 4  # Friday
WEEKEND_CLOSE_HOUR = 20  # 8 PM
WEEKEND_OPEN_DAY = 6  # Sunday
WEEKEND_OPEN_HOUR = 20  # 8 PM


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

    # =========================================================================
    # 24/5 Trading Methods
    # =========================================================================

    def _is_weekend_closure(self) -> bool:
        """
        Check if we're in the weekend closure period.

        24/5 trading is available from Sunday 8 PM ET through Friday 8 PM ET.
        Weekend closure is from Friday 8 PM ET through Sunday 8 PM ET.

        Returns:
            True if in weekend closure period (no trading available)
        """
        now = self._get_market_time()
        weekday = now.weekday()  # Monday = 0, Sunday = 6
        hour = now.hour

        # Friday after 8 PM ET
        if weekday == WEEKEND_CLOSE_DAY and hour >= WEEKEND_CLOSE_HOUR:
            return True

        # Saturday (all day)
        if weekday == 5:  # Saturday
            return True

        # Sunday before 8 PM ET
        if weekday == WEEKEND_OPEN_DAY and hour < WEEKEND_OPEN_HOUR:
            return True

        return False

    def _get_seconds_until_24_5_open(self) -> float:
        """
        Calculate seconds until 24/5 trading window opens.

        Returns:
            Seconds until Sunday 8 PM ET when trading resumes.
            Returns 0 if already within the trading window.
        """
        if not self._is_weekend_closure():
            return 0

        now = self._get_market_time()
        weekday = now.weekday()

        # Calculate next Sunday 8 PM ET
        if weekday == WEEKEND_CLOSE_DAY:  # Friday
            # Next Sunday is 2 days away
            days_until_sunday = 2
        elif weekday == 5:  # Saturday
            # Next Sunday is 1 day away
            days_until_sunday = 1
        else:  # Sunday
            days_until_sunday = 0

        # Create target datetime (Sunday 8 PM ET)
        target = now.replace(
            hour=WEEKEND_OPEN_HOUR,
            minute=0,
            second=0,
            microsecond=0,
        ) + timedelta(days=days_until_sunday)

        seconds_until_open = (target - now).total_seconds()
        return max(0, seconds_until_open)

    def _get_current_session(self) -> TradingSession:
        """Get the current trading session from the broker."""
        return self._broker.get_current_trading_session()

    def _can_trade_in_session(self) -> tuple[bool, str]:
        """
        Check if trading is allowed in the current session based on settings.

        Considers:
        - Weekend closure (no trading Friday 8 PM - Sunday 8 PM ET)
        - Extended hours settings (pre-market, after-hours)
        - Overnight trading settings
        - Circuit breaker status

        Returns:
            Tuple of (can_trade, reason)
        """
        # Check weekend closure first
        if self._is_weekend_closure():
            return False, "Weekend closure (Friday 8 PM - Sunday 8 PM ET)"

        # Get current session
        session = self._get_current_session()
        settings = self._settings

        # Regular hours always allowed
        if session == TradingSession.REGULAR:
            return True, "Regular market hours"

        # Pre-market and after-hours
        if session in (TradingSession.PRE_MARKET, TradingSession.AFTER_HOURS):
            if settings.enable_extended_hours:
                return True, f"{session.value.replace('_', ' ').title()} session"
            return False, f"{session.value.replace('_', ' ').title()} trading disabled"

        # Overnight session
        if session == TradingSession.OVERNIGHT:
            if settings.enable_overnight_trading:
                return True, "Overnight session (LIMIT orders only)"
            return False, "Overnight trading disabled"

        return False, f"Unknown session: {session}"

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

    async def _wait_for_24_5_window(self) -> None:
        """
        Wait for the 24/5 trading window to open (Sunday 8 PM ET).

        During weekend closure (Friday 8 PM - Sunday 8 PM ET), this method
        will sleep efficiently until trading resumes.
        """
        while not self._shutdown_event.is_set() and self._is_weekend_closure():
            seconds_until_open = self._get_seconds_until_24_5_open()

            if seconds_until_open == 0:
                return

            # Sleep in chunks (max 5 minutes) to allow shutdown checks
            sleep_time = min(seconds_until_open, 300)

            hours, remainder = divmod(int(seconds_until_open), 3600)
            minutes, seconds = divmod(remainder, 60)

            if hours > 0:
                time_str = f"{hours}h {minutes}m {seconds}s"
            elif minutes > 0:
                time_str = f"{minutes}m {seconds}s"
            else:
                time_str = f"{seconds}s"

            logger.info(f"Weekend closure - 24/5 trading opens in {time_str}")
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
        """
        Main run loop for the trading agent.

        Supports 24/5 trading:
        - Active from Sunday 8 PM ET through Friday 8 PM ET
        - Sleeps during weekend closure (Friday 8 PM - Sunday 8 PM ET)
        - Respects extended hours and overnight trading settings
        """
        logger.info("Starting Trading Agent with 24/5 support...")
        self._is_running = True
        set_agent_state("is_running", True)

        # Log 24/5 trading configuration
        logger.info(
            f"24/5 Trading Config - "
            f"Extended hours: {self._settings.enable_extended_hours}, "
            f"Overnight trading: {self._settings.enable_overnight_trading}"
        )

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

        # Track last logged session to avoid log spam
        last_session = None
        last_can_trade = None

        # Main loop
        try:
            while not self._shutdown_event.is_set():
                try:
                    # Check weekend closure first
                    if self._is_weekend_closure():
                        logger.info("Weekend closure detected - waiting for Sunday 8 PM ET...")
                        await self._wait_for_24_5_window()

                        if self._shutdown_event.is_set():
                            break
                        continue

                    # We're within the 24/5 window (Sunday 8 PM - Friday 8 PM)
                    current_session = self._get_current_session()
                    can_trade_session, session_reason = self._can_trade_in_session()

                    # Log session changes
                    if current_session != last_session:
                        logger.info(f"Session change: {current_session.value} - {session_reason}")
                        last_session = current_session

                    # Log trading availability changes
                    if can_trade_session != last_can_trade:
                        if can_trade_session:
                            logger.info(f"Trading ENABLED: {session_reason}")
                        else:
                            logger.info(f"Trading DISABLED: {session_reason}")
                        last_can_trade = can_trade_session

                    # If we can trade in this session, run the trading loop
                    if can_trade_session:
                        # Check circuit breaker
                        can_trade_cb, cb_reason = self._circuit_breaker.can_trade()
                        if not can_trade_cb:
                            logger.warning(f"Circuit breaker active: {cb_reason}")
                            await asyncio.sleep(60)
                            continue

                        # Check strategies for auto-disable
                        await self._check_strategies()

                        # Process strategies
                        # In a real implementation, this would:
                        # 1. Get market data (use appropriate feed for session)
                        # 2. Pass to strategies for signal generation
                        # 3. Validate signals (check order type restrictions for overnight)
                        # 4. Execute trades (LIMIT only for overnight session)
                        # 5. Monitor positions

                        # Note: During overnight session, only LIMIT orders with
                        # DAY or GTC TIF are supported. Strategies should be aware
                        # of this and adjust their order types accordingly.

                        # Trading loop runs every second during active sessions
                        await asyncio.sleep(1)
                    else:
                        # Can't trade in this session, but stay awake to monitor
                        # Check every 30 seconds for session changes
                        await asyncio.sleep(30)

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
    logger.info("24/5 Trading Enabled")
    logger.info("=" * 60)

    settings = get_settings()
    logger.info(f"Environment: {settings.environment}")
    logger.info(f"Trading Mode: {settings.trading_mode}")
    logger.info(f"Paper Trading Capital: ${settings.paper_trading_capital:,.2f}")
    logger.info("-" * 60)
    logger.info("24/5 Trading Configuration:")
    logger.info(f"  Extended Hours (4AM-8PM ET): {settings.enable_extended_hours}")
    logger.info(f"  Overnight Trading (8PM-4AM ET): {settings.enable_overnight_trading}")
    logger.info("  Trading Window: Sunday 8 PM ET - Friday 8 PM ET")
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
