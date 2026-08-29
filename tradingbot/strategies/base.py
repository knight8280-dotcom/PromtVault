"""Strategy base class and the registry the CLI resolves names against."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

from ..models import HOLD, Candle, Position, Signal


class Strategy(ABC):
    """A strategy turns a window of candles into an intent for the latest bar.

    Implementations must be pure: given the same candles and position they return
    the same signal, and they never place orders themselves. That keeps the same
    code path valid for backtesting, paper trading and live trading.
    """

    #: Human-readable name used in configs and on the CLI.
    name: str = "base"
    #: Defaults merged with user params; also documents what the strategy accepts.
    default_params: dict[str, Any] = {}

    def __init__(self, **params: Any) -> None:
        unknown = set(params) - set(self.default_params)
        if unknown:
            raise ValueError(
                f"{self.name}: unknown parameter(s) {', '.join(sorted(unknown))}; "
                f"accepted: {', '.join(sorted(self.default_params)) or 'none'}"
            )
        self.params = {**self.default_params, **params}
        self.validate_params()

    def validate_params(self) -> None:
        """Override to reject nonsensical parameter combinations at startup."""

    @property
    @abstractmethod
    def warmup(self) -> int:
        """Bars required before `generate` can produce a non-HOLD signal."""

    @abstractmethod
    def generate(self, candles: Sequence[Candle], position: Position | None) -> Signal:
        """Return the intent for `candles[-1]`.

        `candles` is ordered oldest-first and only contains closed bars, so a
        strategy can never peek at data it would not have had in real time.
        """

    def _hold(self) -> Signal:
        return HOLD

    def describe(self) -> str:
        params = ", ".join(f"{k}={v}" for k, v in sorted(self.params.items()))
        return f"{self.name}({params})"


_REGISTRY: dict[str, type[Strategy]] = {}


def register(cls: type[Strategy]) -> type[Strategy]:
    """Class decorator that makes a strategy resolvable by name."""
    if cls.name in _REGISTRY and _REGISTRY[cls.name] is not cls:
        raise ValueError(f"strategy name {cls.name!r} is already registered")
    _REGISTRY[cls.name] = cls
    return cls


def get_strategy(name: str, **params: Any) -> Strategy:
    """Instantiate a registered strategy by name."""
    if name not in _REGISTRY:
        raise KeyError(f"unknown strategy {name!r}; available: {', '.join(available_strategies())}")
    return _REGISTRY[name](**params)


def available_strategies() -> list[str]:
    return sorted(_REGISTRY)


def strategy_class(name: str) -> type[Strategy]:
    if name not in _REGISTRY:
        raise KeyError(f"unknown strategy {name!r}; available: {', '.join(available_strategies())}")
    return _REGISTRY[name]
