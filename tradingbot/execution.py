"""Fee tiers and order-type economics.

The cost sensitivity sweep in `validate` kept delivering the same verdict: the
bundled strategies are profitable at zero fees and unprofitable at real ones. That
is not a strategy problem, it is an execution problem, and it has a real fix.

Taker orders cross the spread and pay the taker fee. Maker orders rest on the book
and pay the (much lower, sometimes negative) maker fee — at the cost of not always
filling. For a carry trade held for days, waiting for a maker fill is nearly free.
For a breakout entry, missing the fill can cost more than the fee saved.

This module makes that trade-off explicit and measurable rather than assumed.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Liquidity(str, Enum):
    """Which side of the book an order took."""

    MAKER = "maker"
    TAKER = "taker"


@dataclass(frozen=True)
class FeeTier:
    """A venue's fee schedule at one volume level.

    Maker fees are negative on venues that pay rebates; the arithmetic here
    handles that correctly, since a rebate flips the sign of the cost.
    """

    name: str
    maker: float
    taker: float

    def rate_for(self, liquidity: Liquidity) -> float:
        return self.maker if liquidity is Liquidity.MAKER else self.taker

    @property
    def maker_saving(self) -> float:
        """How much each maker fill saves versus taking, as a fraction."""
        return self.taker - self.maker

    def round_trip(self, liquidity: Liquidity) -> float:
        return 2 * self.rate_for(liquidity)


#: Representative published spot tiers. Check your own — they change and they
#: vary by volume, by token holdings, and by whether you are on a promotion.
FEE_TIERS = {
    "binance": FeeTier("binance spot VIP0", maker=0.0010, taker=0.0010),
    "binance_bnb": FeeTier("binance spot with BNB discount", maker=0.00075, taker=0.00075),
    "binance_perp": FeeTier("binance USD-M futures VIP0", maker=0.0002, taker=0.0005),
    "bybit_perp": FeeTier("bybit perpetual", maker=0.0002, taker=0.00055),
    "okx_perp": FeeTier("okx perpetual", maker=0.0002, taker=0.0005),
    "coinbase": FeeTier("coinbase advanced", maker=0.0060, taker=0.0080),
    "kraken": FeeTier("kraken spot", maker=0.0016, taker=0.0026),
    "zero": FeeTier("zero-fee (modelling only)", maker=0.0, taker=0.0),
}


def get_tier(name: str) -> FeeTier:
    if name not in FEE_TIERS:
        raise KeyError(f"unknown fee tier {name!r}; known: {', '.join(sorted(FEE_TIERS))}")
    return FEE_TIERS[name]


@dataclass
class ExecutionModel:
    """Models what an order actually costs, given how it is placed.

    `maker_fill_rate` is the share of resting orders that fill before the signal
    goes stale. It is the honest cost of maker execution: orders that do not fill
    are trades you did not make, and pretending otherwise is how a backtest starts
    lying.
    """

    tier: FeeTier
    prefer_maker: bool = False
    maker_fill_rate: float = 0.7
    # Taker orders cross the spread; makers earn it instead of paying it.
    spread_pct: float = 0.0002

    def __post_init__(self) -> None:
        if not 0 <= self.maker_fill_rate <= 1:
            raise ValueError("maker_fill_rate must be between 0 and 1")
        if self.spread_pct < 0:
            raise ValueError("spread_pct cannot be negative")

    def effective_fee(self) -> float:
        """Expected fee per fill, blending maker and taker outcomes."""
        if not self.prefer_maker:
            return self.tier.taker
        return (
            self.maker_fill_rate * self.tier.maker
            + (1 - self.maker_fill_rate) * self.tier.taker
        )

    def effective_slippage(self) -> float:
        """Expected slippage per fill.

        A maker order that fills does so at its own price, earning the spread
        rather than paying it; one that does not fill gets swept up as a taker.
        """
        if not self.prefer_maker:
            return self.spread_pct
        return (1 - self.maker_fill_rate) * self.spread_pct

    def round_trip_cost(self) -> float:
        """Total expected cost of opening and closing, as a fraction."""
        return 2 * (self.effective_fee() + self.effective_slippage())

    def saving_vs_taker(self) -> float:
        """How much a round trip saves against pure taker execution."""
        taker = ExecutionModel(self.tier, prefer_maker=False, spread_pct=self.spread_pct)
        return taker.round_trip_cost() - self.round_trip_cost()

    def describe(self) -> str:
        mode = (
            f"maker-preferred ({self.maker_fill_rate:.0%} fill rate)"
            if self.prefer_maker else "taker"
        )
        return (
            f"{self.tier.name}, {mode}: effective fee {self.effective_fee():.4%}, "
            f"round trip {self.round_trip_cost():.4%}"
        )


def breakeven_edge_per_trade(model: ExecutionModel) -> float:
    """The gross move a trade must capture just to break even, as a percentage.

    Useful as a sanity check on a strategy: if the average winner is smaller than
    this, the strategy cannot be profitable no matter how often it is right.
    """
    return model.round_trip_cost() * 100


def compare_execution(tier: FeeTier, fill_rates: list[float] | None = None) -> list[dict]:
    """Table of taker versus maker execution across assumed fill rates."""
    rates = fill_rates or [0.5, 0.7, 0.9, 1.0]
    taker = ExecutionModel(tier, prefer_maker=False)

    rows = [
        {
            "mode": "taker",
            "fill_rate": 1.0,
            "effective_fee": taker.effective_fee(),
            "round_trip": taker.round_trip_cost(),
            "breakeven_pct": breakeven_edge_per_trade(taker),
            "saving": 0.0,
        }
    ]
    for rate in rates:
        model = ExecutionModel(tier, prefer_maker=True, maker_fill_rate=rate)
        rows.append(
            {
                "mode": "maker",
                "fill_rate": rate,
                "effective_fee": model.effective_fee(),
                "round_trip": model.round_trip_cost(),
                "breakeven_pct": breakeven_edge_per_trade(model),
                "saving": model.saving_vs_taker(),
            }
        )
    return rows
