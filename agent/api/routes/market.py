"""Market status API endpoints."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter
from loguru import logger
from pydantic import BaseModel

from agent.config.constants import TradingSession
from agent.execution.broker import AlpacaBroker

router = APIRouter()

# Lazy-initialized broker for market status checks
_broker: AlpacaBroker | None = None


def get_broker() -> AlpacaBroker:
    """Get or create broker instance for market checks."""
    global _broker
    if _broker is None:
        _broker = AlpacaBroker()
    return _broker


class MarketStatusResponse(BaseModel):
    """Market status response."""

    is_open: bool
    current_session: str
    session_display: str
    next_open: str | None
    next_close: str | None
    timestamp: str
    can_trade_regular: bool
    can_trade_extended: bool
    can_trade_overnight: bool


class AssetInfoResponse(BaseModel):
    """Asset information response."""

    symbol: str
    name: str | None
    exchange: str | None
    status: str | None
    tradable: bool
    fractionable: bool
    marginable: bool
    shortable: bool
    easy_to_borrow: bool
    overnight_tradable: bool
    has_options: bool


@router.get("/status", response_model=MarketStatusResponse)
async def get_market_status() -> MarketStatusResponse:
    """
    Get current market status including session info.

    Returns real-time market status from Alpaca including:
    - Whether the market is currently open
    - Current trading session (overnight, pre-market, regular, after-hours)
    - Next open/close times
    - Trading eligibility for each session type
    """
    try:
        broker = get_broker()

        # Get market hours from Alpaca
        market_hours = broker.get_market_hours()
        is_open = market_hours.get("is_open", False) if market_hours else False
        next_open = market_hours.get("next_open") if market_hours else None
        next_close = market_hours.get("next_close") if market_hours else None

        # Get current session
        session = broker.get_current_trading_session()

        # Session display names
        session_displays = {
            TradingSession.OVERNIGHT: "Overnight (8PM-4AM ET)",
            TradingSession.PRE_MARKET: "Pre-Market (4AM-9:30AM ET)",
            TradingSession.REGULAR: "Regular Hours (9:30AM-4PM ET)",
            TradingSession.AFTER_HOURS: "After Hours (4PM-8PM ET)",
        }

        return MarketStatusResponse(
            is_open=is_open,
            current_session=session.value,
            session_display=session_displays.get(session, session.value),
            next_open=next_open,
            next_close=next_close,
            timestamp=datetime.now().isoformat(),
            can_trade_regular=session == TradingSession.REGULAR,
            can_trade_extended=session
            in (
                TradingSession.PRE_MARKET,
                TradingSession.REGULAR,
                TradingSession.AFTER_HOURS,
            ),
            can_trade_overnight=True,  # 24/5 trading available Sun 8PM - Fri 8PM
        )

    except Exception as e:
        logger.error(f"Failed to get market status: {e}")
        # Return a default response on error
        return MarketStatusResponse(
            is_open=False,
            current_session="unknown",
            session_display="Unknown (API Error)",
            next_open=None,
            next_close=None,
            timestamp=datetime.now().isoformat(),
            can_trade_regular=False,
            can_trade_extended=False,
            can_trade_overnight=False,
        )


@router.get("/asset/{symbol}", response_model=AssetInfoResponse)
async def get_asset_info(symbol: str) -> AssetInfoResponse:
    """
    Get detailed asset information including trading eligibility.

    Args:
        symbol: Stock ticker symbol (e.g., SPY, AAPL)

    Returns:
        Asset details including overnight tradability
    """
    try:
        broker = get_broker()
        info = broker.get_asset_info(symbol.upper())

        if not info:
            return AssetInfoResponse(
                symbol=symbol.upper(),
                name=None,
                exchange=None,
                status="not_found",
                tradable=False,
                fractionable=False,
                marginable=False,
                shortable=False,
                easy_to_borrow=False,
                overnight_tradable=False,
                has_options=False,
            )

        return AssetInfoResponse(
            symbol=info["symbol"],
            name=info.get("name"),
            exchange=info.get("exchange"),
            status=info.get("status"),
            tradable=info.get("tradable", False),
            fractionable=info.get("fractionable", False),
            marginable=info.get("marginable", False),
            shortable=info.get("shortable", False),
            easy_to_borrow=info.get("easy_to_borrow", False),
            overnight_tradable=info.get("overnight_tradable", False),
            has_options=info.get("has_options", False),
        )

    except Exception as e:
        logger.error(f"Failed to get asset info for {symbol}: {e}")
        return AssetInfoResponse(
            symbol=symbol.upper(),
            name=None,
            exchange=None,
            status="error",
            tradable=False,
            fractionable=False,
            marginable=False,
            shortable=False,
            easy_to_borrow=False,
            overnight_tradable=False,
            has_options=False,
        )


@router.get("/quote/{symbol}")
async def get_quote(symbol: str) -> dict[str, Any]:
    """
    Get latest quote for a symbol.

    Args:
        symbol: Stock ticker symbol

    Returns:
        Latest bid/ask quote
    """
    try:
        broker = get_broker()
        quote = broker.get_latest_quote(symbol.upper())

        if not quote:
            return {
                "symbol": symbol.upper(),
                "error": "Quote not available",
                "timestamp": datetime.now().isoformat(),
            }

        return quote

    except Exception as e:
        logger.error(f"Failed to get quote for {symbol}: {e}")
        return {
            "symbol": symbol.upper(),
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }
