"""Trading strategies for the Bringetto Trading Agent."""

from agent.strategies.base import BaseStrategy, StrategySignal
from agent.strategies.orb import OpeningRangeBreakout
from agent.strategies.vwap_reversion import VWAPReversion
from agent.strategies.momentum_scalp import MomentumScalp
from agent.strategies.gap_and_go import GapAndGo
from agent.strategies.eod_reversal import EODReversal

__all__ = [
    "BaseStrategy",
    "StrategySignal",
    "OpeningRangeBreakout",
    "VWAPReversion",
    "MomentumScalp",
    "GapAndGo",
    "EODReversal",
]
