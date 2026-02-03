"""Agent state management - shared between main.py and API routes."""

from typing import Any

# Global state (will be set by main.py)
_agent_state: dict[str, Any] = {
    "broker": None,
    "circuit_breaker": None,
    "strategies": [],
    "is_running": False,
}


def get_agent_state() -> dict[str, Any]:
    """Get the current agent state."""
    return _agent_state


def set_agent_state(key: str, value: Any) -> None:
    """Set a value in the agent state."""
    _agent_state[key] = value
