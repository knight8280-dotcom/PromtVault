"""Strategy package. Importing it registers every bundled strategy."""

from .base import Strategy, available_strategies, get_strategy, register, strategy_class
from .breakout import BreakoutStrategy
from .rsi_reversion import RsiReversionStrategy
from .sma_cross import SmaCrossStrategy

__all__ = [
    "Strategy",
    "available_strategies",
    "get_strategy",
    "register",
    "strategy_class",
    "BreakoutStrategy",
    "RsiReversionStrategy",
    "SmaCrossStrategy",
]
