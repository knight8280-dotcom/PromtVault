"""Configuration loading and validation.

Config comes from a YAML file; secrets never do. API keys are read from the
environment only, so a config file is always safe to commit or share.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

try:  # PyYAML is the only hard dependency, but degrade with a clear message.
    import yaml
except ImportError:  # pragma: no cover - exercised only in broken installs
    yaml = None


class ConfigError(Exception):
    """Raised when configuration is missing, malformed or unsafe."""


VALID_TIMEFRAMES = {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"}


@dataclass
class ExchangeConfig:
    name: str = "binance"
    # Env var names, not the secrets themselves.
    api_key_env: str = "EXCHANGE_API_KEY"
    api_secret_env: str = "EXCHANGE_API_SECRET"
    api_password_env: str = "EXCHANGE_API_PASSWORD"
    testnet: bool = True
    rate_limit: bool = True

    def credentials(self) -> dict[str, str]:
        """Read credentials from the environment. Missing values stay absent."""
        creds = {}
        if key := os.environ.get(self.api_key_env):
            creds["apiKey"] = key
        if secret := os.environ.get(self.api_secret_env):
            creds["secret"] = secret
        if password := os.environ.get(self.api_password_env):
            creds["password"] = password
        return creds


@dataclass
class RiskConfig:
    # Fraction of equity risked per trade, given the distance to the stop.
    risk_per_trade: float = 0.01
    # Hard ceiling on a single position's notional as a fraction of equity.
    max_position_pct: float = 0.20
    # Total gross exposure ceiling across all open positions.
    max_total_exposure_pct: float = 0.60
    max_open_positions: int = 3
    # Trading halts for the day once realized losses exceed this fraction.
    max_daily_loss_pct: float = 0.05
    # Trading halts permanently once equity falls this far below its peak.
    max_drawdown_pct: float = 0.20
    # Default protective stop when a strategy does not supply one.
    stop_loss_pct: float = 0.02
    take_profit_pct: float | None = 0.04
    # Trailing stop distance as a fraction of price; None disables trailing.
    trailing_stop_pct: float | None = None
    allow_shorts: bool = False

    def validate(self) -> None:
        if not 0 < self.risk_per_trade <= 0.1:
            raise ConfigError("risk.risk_per_trade must be in (0, 0.1] — risking more per trade is not supported")
        for name in ("max_position_pct", "max_total_exposure_pct", "max_daily_loss_pct", "max_drawdown_pct"):
            value = getattr(self, name)
            if not 0 < value <= 1:
                raise ConfigError(f"risk.{name} must be in (0, 1]")
        if self.max_open_positions < 1:
            raise ConfigError("risk.max_open_positions must be at least 1")
        if self.stop_loss_pct <= 0:
            raise ConfigError("risk.stop_loss_pct must be positive")
        if self.max_position_pct > self.max_total_exposure_pct:
            raise ConfigError("risk.max_position_pct cannot exceed risk.max_total_exposure_pct")


@dataclass
class ExecutionConfig:
    # "paper" simulates fills locally; "live" sends real orders.
    mode: str = "paper"
    starting_cash: float = 10_000.0
    # Taker fee per side, as a fraction of notional.
    fee_rate: float = 0.001
    # Modelled slippage for market orders, as a fraction of price.
    slippage_pct: float = 0.0005
    # Seconds between polls of the live loop.
    poll_interval: int = 60
    # Refuse to place an order smaller than this notional.
    min_order_notional: float = 10.0
    # Named fee tier from tradingbot.execution.FEE_TIERS. When set, it overrides
    # fee_rate and slippage_pct with the modelled cost of your actual execution.
    fee_tier: str | None = None
    # Rest orders on the book instead of crossing the spread. Much cheaper, but
    # only sound when a missed fill costs less than the fee saved.
    prefer_maker: bool = False
    # Share of resting orders expected to fill before the signal goes stale.
    maker_fill_rate: float = 0.7
    # Live trading additionally requires this to be true. Two locks, on purpose.
    confirm_live: bool = False

    def validate(self) -> None:
        if self.mode not in ("paper", "live"):
            raise ConfigError("execution.mode must be 'paper' or 'live'")
        if self.starting_cash <= 0:
            raise ConfigError("execution.starting_cash must be positive")
        if self.fee_rate < 0 or self.slippage_pct < 0:
            raise ConfigError("execution.fee_rate and slippage_pct cannot be negative")
        if self.poll_interval < 1:
            raise ConfigError("execution.poll_interval must be at least 1 second")
        if not 0 <= self.maker_fill_rate <= 1:
            raise ConfigError("execution.maker_fill_rate must be between 0 and 1")
        if self.fee_tier is not None:
            from .execution import FEE_TIERS

            if self.fee_tier not in FEE_TIERS:
                raise ConfigError(
                    f"unknown execution.fee_tier {self.fee_tier!r}; "
                    f"known: {', '.join(sorted(FEE_TIERS))}"
                )

    def execution_model(self):
        """The modelled cost of this execution setup, or None if not configured."""
        if self.fee_tier is None:
            return None
        from .execution import ExecutionModel, get_tier

        return ExecutionModel(
            get_tier(self.fee_tier),
            prefer_maker=self.prefer_maker,
            maker_fill_rate=self.maker_fill_rate,
        )

    def apply_fee_tier(self) -> None:
        """Derive fee_rate and slippage_pct from the fee tier, when one is set."""
        model = self.execution_model()
        if model is not None:
            self.fee_rate = model.effective_fee()
            self.slippage_pct = model.effective_slippage()


@dataclass
class StrategyConfig:
    name: str = "sma_cross"
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class Config:
    symbols: list[str] = field(default_factory=lambda: ["BTC/USDT"])
    timeframe: str = "1h"
    exchange: ExchangeConfig = field(default_factory=ExchangeConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    log_level: str = "INFO"
    state_dir: str = "state"
    data_dir: str = "data_cache"

    def validate(self) -> None:
        if not self.symbols:
            raise ConfigError("at least one symbol is required")
        for symbol in self.symbols:
            if "/" not in symbol:
                raise ConfigError(f"symbol {symbol!r} must be in BASE/QUOTE form, e.g. BTC/USDT")
        if self.timeframe not in VALID_TIMEFRAMES:
            raise ConfigError(
                f"timeframe {self.timeframe!r} is not supported; expected one of {sorted(VALID_TIMEFRAMES)}"
            )
        self.risk.validate()
        self.execution.validate()
        # A configured tier is the source of truth for costs, so resolve it once
        # here rather than leaving two contradictory numbers in the config.
        self.execution.apply_fee_tier()

    @property
    def is_live(self) -> bool:
        return self.execution.mode == "live"


def _build(cls, data: dict[str, Any], path: str):
    """Instantiate a dataclass from a mapping, rejecting unknown keys."""
    known = {f.name for f in fields(cls)}
    unknown = set(data) - known
    if unknown:
        raise ConfigError(f"unknown key(s) in {path}: {', '.join(sorted(unknown))}")
    return cls(**data)


def load_config(path: str | Path) -> Config:
    """Load and validate a YAML config file."""
    if yaml is None:
        raise ConfigError("PyYAML is required to load config files: pip install PyYAML")

    path = Path(path)
    if not path.exists():
        raise ConfigError(f"config file not found: {path}")

    raw = yaml.safe_load(path.read_text()) or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"config file {path} must contain a YAML mapping")

    return from_dict(raw)


def from_dict(raw: dict[str, Any]) -> Config:
    """Build a validated Config from a plain mapping."""
    raw = dict(raw)
    nested = {
        "exchange": ExchangeConfig,
        "strategy": StrategyConfig,
        "risk": RiskConfig,
        "execution": ExecutionConfig,
    }
    kwargs: dict[str, Any] = {}
    for key, cls in nested.items():
        section = raw.pop(key, {}) or {}
        if not isinstance(section, dict):
            raise ConfigError(f"config section {key!r} must be a mapping")
        kwargs[key] = _build(cls, section, key)

    if isinstance(raw.get("symbols"), str):  # tolerate a single symbol as a string
        raw["symbols"] = [raw["symbols"]]

    config = _build(Config, {**raw, **kwargs}, "top level")
    config.validate()
    return config
