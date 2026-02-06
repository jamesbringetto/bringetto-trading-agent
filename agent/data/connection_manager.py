"""Central WebSocket connection coordinator for Alpaca streams.

Alpaca's free/paper tier allows only 1 concurrent WebSocket connection per
stream type (stock data, trading).  When a connection fails, the server-side
socket can linger for 60-120+ seconds before Alpaca considers it closed.

This module provides a singleton ``ConnectionManager`` that:

1. Enforces a **global cooldown** between connection attempts per stream type,
   preventing rapid reconnection loops that exceed Alpaca's limit.
2. Tracks **consecutive connection-limit failures** and escalates the backoff
   (120 s → 240 s → 480 s → …) so the agent does not hammer a limit that
   cannot be resolved by retrying faster.
3. Serialises reconnection attempts across stream types so that the data
   stream and trading stream never try to connect simultaneously (which would
   double the load on the connection-limit window).
4. Does **not** count connection-limit errors toward the "max reconnect
   attempts" counter, because they are a transient server-side condition,
   not a permanent failure.
"""

from __future__ import annotations

import asyncio
import time as _time
from enum import StrEnum

from loguru import logger


class StreamType(StrEnum):
    """Alpaca WebSocket stream types."""

    STOCK_DATA = "stock_data"
    TRADING = "trading"


# ---------------------------------------------------------------------------
# Backoff configuration
# ---------------------------------------------------------------------------

# Minimum cooldown after closing a connection before opening a new one.
# This gives the server time to recognise the old socket as dead.
MIN_CLOSE_COOLDOWN_SECONDS = 10.0

# Base backoff when Alpaca returns "connection limit exceeded".
CONNECTION_LIMIT_BASE_BACKOFF = 120.0  # 2 minutes

# Multiplier per consecutive connection-limit failure (exponential).
CONNECTION_LIMIT_BACKOFF_MULTIPLIER = 2.0

# Absolute cap for the connection-limit backoff.
CONNECTION_LIMIT_MAX_BACKOFF = 600.0  # 10 minutes

# Standard reconnection parameters (non-connection-limit errors).
STANDARD_INITIAL_DELAY = 2.0
STANDARD_MAX_DELAY = 60.0


class _StreamState:
    """Per-stream connection tracking."""

    __slots__ = (
        "stream_type",
        "last_close_time",
        "last_connect_attempt_time",
        "consecutive_conn_limit_failures",
        "cooldown_until",
    )

    def __init__(self, stream_type: StreamType) -> None:
        self.stream_type = stream_type
        self.last_close_time: float = 0.0
        self.last_connect_attempt_time: float = 0.0
        self.consecutive_conn_limit_failures: int = 0
        # Absolute monotonic timestamp before which no connection should be
        # attempted.
        self.cooldown_until: float = 0.0


class ConnectionManager:
    """Singleton coordinator for Alpaca WebSocket connections.

    Usage::

        mgr = get_connection_manager()

        # Before each connection attempt:
        await mgr.wait_for_clearance(StreamType.STOCK_DATA)

        # After a successful connection (resets counters):
        mgr.record_connected(StreamType.STOCK_DATA)

        # After a disconnection:
        mgr.record_disconnected(StreamType.STOCK_DATA)

        # After a "connection limit exceeded" error:
        mgr.record_connection_limit_error(StreamType.STOCK_DATA)
    """

    def __init__(self) -> None:
        self._states: dict[StreamType, _StreamState] = {st: _StreamState(st) for st in StreamType}
        # Serialise connection attempts across ALL stream types so only one
        # stream tries to connect at a time.
        self._connect_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def wait_for_clearance(self, stream_type: StreamType) -> None:
        """Block until it is safe to attempt a new connection.

        This method:
        1. Acquires the global connect lock (so only one stream connects at a
           time).
        2. Waits for any active cooldown to expire.
        3. Waits for the minimum close-cooldown if the previous connection was
           closed recently.
        4. Records the connection-attempt timestamp.

        The lock is released immediately so callers can proceed with the
        actual connection.  The lock merely *serialises* the decision of
        "who goes next" — it does not stay held while the connection is
        active.
        """
        async with self._connect_lock:
            state = self._states[stream_type]
            now = _time.monotonic()

            # 1. Wait for cooldown (from connection-limit errors)
            if state.cooldown_until > now:
                wait = state.cooldown_until - now
                logger.info(
                    f"[ConnectionManager] {stream_type.value}: "
                    f"waiting {wait:.0f}s cooldown before reconnecting"
                )
                await asyncio.sleep(wait)

            # 2. Enforce minimum delay since last close
            since_close = _time.monotonic() - state.last_close_time
            if since_close < MIN_CLOSE_COOLDOWN_SECONDS and state.last_close_time > 0:
                wait = MIN_CLOSE_COOLDOWN_SECONDS - since_close
                logger.debug(
                    f"[ConnectionManager] {stream_type.value}: waiting {wait:.1f}s close-cooldown"
                )
                await asyncio.sleep(wait)

            state.last_connect_attempt_time = _time.monotonic()
            logger.info(f"[ConnectionManager] {stream_type.value}: clearance granted")

    def record_connected(self, stream_type: StreamType) -> None:
        """Call after a successful connection + authentication."""
        state = self._states[stream_type]
        state.consecutive_conn_limit_failures = 0
        logger.info(
            f"[ConnectionManager] {stream_type.value}: connected — connection-limit counter reset"
        )

    def record_disconnected(self, stream_type: StreamType) -> None:
        """Call after a stream is closed/disconnected."""
        state = self._states[stream_type]
        state.last_close_time = _time.monotonic()
        logger.debug(f"[ConnectionManager] {stream_type.value}: disconnected")

    def record_connection_limit_error(self, stream_type: StreamType) -> None:
        """Call when "connection limit exceeded" is detected.

        Sets an escalating cooldown before the next connection attempt.
        """
        state = self._states[stream_type]
        state.consecutive_conn_limit_failures += 1
        n = state.consecutive_conn_limit_failures

        backoff = min(
            CONNECTION_LIMIT_BASE_BACKOFF * (CONNECTION_LIMIT_BACKOFF_MULTIPLIER ** (n - 1)),
            CONNECTION_LIMIT_MAX_BACKOFF,
        )
        state.cooldown_until = _time.monotonic() + backoff

        logger.warning(
            f"[ConnectionManager] {stream_type.value}: "
            f"connection limit error #{n} — cooldown {backoff:.0f}s "
            f"(next attempt no earlier than {backoff:.0f}s from now)"
        )

    def get_connection_limit_backoff(self, stream_type: StreamType) -> float:
        """Return the current backoff duration for connection-limit errors."""
        state = self._states[stream_type]
        n = max(state.consecutive_conn_limit_failures, 1)
        return min(
            CONNECTION_LIMIT_BASE_BACKOFF * (CONNECTION_LIMIT_BACKOFF_MULTIPLIER ** (n - 1)),
            CONNECTION_LIMIT_MAX_BACKOFF,
        )

    def get_status(self) -> dict[str, dict]:
        """Return status for monitoring/health endpoints."""
        now = _time.monotonic()
        result = {}
        for st, state in self._states.items():
            cooldown_remaining = max(0.0, state.cooldown_until - now)
            result[st.value] = {
                "consecutive_conn_limit_failures": state.consecutive_conn_limit_failures,
                "cooldown_remaining_seconds": round(cooldown_remaining, 1),
                "seconds_since_last_close": (
                    round(now - state.last_close_time, 1) if state.last_close_time > 0 else None
                ),
            }
        return result


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_instance: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    """Return the global ConnectionManager singleton."""
    global _instance
    if _instance is None:
        _instance = ConnectionManager()
    return _instance
