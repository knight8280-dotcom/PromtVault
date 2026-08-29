"""Value objects for funding-rate carry.

Carry is a different animal from the price-prediction strategies elsewhere in
this bot. A perpetual swap has no expiry, so exchanges use a funding payment to
tether it to spot: when the perp trades above spot, longs pay shorts, and vice
versa. Holding long spot and short perp in equal size leaves you flat on price
and collecting (or paying) that funding.

The edge is structural — it is a fee for providing balance sheet, not a forecast.
That is why it is measurable in advance, and why it is worth building around.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

#: Most venues settle funding every 8 hours. Some use 1h or 4h; read it per venue.
DEFAULT_FUNDING_INTERVAL_HOURS = 8
HOURS_PER_YEAR = 24 * 365


@dataclass(frozen=True)
class FundingRate:
    """One funding observation for one perpetual market."""

    symbol: str
    venue: str
    rate: float                      # per interval, as a fraction (0.0001 = 1bp)
    timestamp: datetime
    interval_hours: float = DEFAULT_FUNDING_INTERVAL_HOURS
    next_funding: datetime | None = None
    mark_price: float | None = None
    index_price: float | None = None

    @property
    def annualized_pct(self) -> float:
        """Funding expressed as an annual percentage rate.

        Simple, not compounded: funding is a cash payment, and compounding it
        would overstate what you can actually collect.
        """
        if self.interval_hours <= 0:
            return 0.0
        return self.rate * (HOURS_PER_YEAR / self.interval_hours) * 100

    @property
    def basis_pct(self) -> float | None:
        """How far the perp trades from the index, as a percentage."""
        if not self.mark_price or not self.index_price:
            return None
        return (self.mark_price / self.index_price - 1) * 100

    @property
    def shorts_get_paid(self) -> bool:
        """Positive funding means longs pay shorts, so the carry trade is short perp."""
        return self.rate > 0


@dataclass
class FundingHistory:
    """A window of funding observations, used to judge stability rather than luck."""

    symbol: str
    venue: str
    rates: list[FundingRate] = field(default_factory=list)

    @property
    def mean_rate(self) -> float:
        return sum(r.rate for r in self.rates) / len(self.rates) if self.rates else 0.0

    @property
    def mean_annualized_pct(self) -> float:
        if not self.rates:
            return 0.0
        return sum(r.annualized_pct for r in self.rates) / len(self.rates)

    @property
    def positive_share(self) -> float:
        """Fraction of intervals where funding favoured the short side.

        A high average driven by a handful of spikes is not a carry you can plan
        around; consistency is what makes it bankable.
        """
        if not self.rates:
            return 0.0
        return sum(1 for r in self.rates if r.rate > 0) / len(self.rates)

    @property
    def volatility(self) -> float:
        """Standard deviation of the funding rate across the window."""
        if len(self.rates) < 2:
            return 0.0
        mean = self.mean_rate
        variance = sum((r.rate - mean) ** 2 for r in self.rates) / (len(self.rates) - 1)
        return variance**0.5

    @property
    def worst_rate(self) -> float:
        return min((r.rate for r in self.rates), default=0.0)

    @property
    def intervals(self) -> int:
        return len(self.rates)


@dataclass
class CarryCosts:
    """Everything that eats the funding you collect."""

    spot_fee: float = 0.001          # taker fee on the spot leg, each way
    perp_fee: float = 0.0005         # taker fee on the perp leg, each way
    slippage_pct: float = 0.0005     # per leg, each way
    borrow_apr: float = 0.0          # cost of margin, if the perp leg is financed

    @property
    def round_trip_cost(self) -> float:
        """Total fraction lost to opening and closing both legs."""
        one_way = self.spot_fee + self.perp_fee + 2 * self.slippage_pct
        return one_way * 2


@dataclass
class CarryOpportunity:
    """A funding trade, priced net of what it costs to run."""

    symbol: str
    venue: str
    funding: FundingRate
    history: FundingHistory | None = None
    costs: CarryCosts = field(default_factory=CarryCosts)
    spot_price: float | None = None
    liquidity_note: str = ""
    # How long you are willing to wait to cover the round trip. Breakeven is only
    # meaningful against an intended holding period: 3 days to cover fees is fine
    # for a carry you will hold for weeks and fatal for one you will hold overnight.
    max_breakeven_hours: float = 120.0

    @property
    def gross_annualized_pct(self) -> float:
        """Annualised funding before costs, using history when available.

        The historical mean is preferred over the current print: a single
        observation is noise, and you are underwriting the next few days, not
        the last eight hours.
        """
        if self.history and self.history.intervals >= 3:
            return abs(self.history.mean_annualized_pct)
        return abs(self.funding.annualized_pct)

    @property
    def net_annualized_pct(self) -> float:
        """Carry after fees and borrow, assuming the position is held a year.

        Held for less, the round-trip cost is amortised over a shorter window and
        bites harder — see `net_annualized_for`.
        """
        return self.net_annualized_for(HOURS_PER_YEAR)

    def net_annualized_for(self, holding_hours: float) -> float:
        """Annualised return net of costs for a specific holding period."""
        if holding_hours <= 0:
            return 0.0
        gross_for_period = self.gross_annualized_pct * (holding_hours / HOURS_PER_YEAR)
        cost_pct = self.costs.round_trip_cost * 100
        borrow_pct = self.costs.borrow_apr * 100 * (holding_hours / HOURS_PER_YEAR)
        net_for_period = gross_for_period - cost_pct - borrow_pct
        return net_for_period * (HOURS_PER_YEAR / holding_hours)

    @property
    def breakeven_hours(self) -> float | None:
        """How long you must hold before funding covers the round trip.

        This is the number that kills most carry trades: a 10% APR looks fine
        until you notice it takes four days just to pay for entering.
        """
        gross = self.gross_annualized_pct
        if gross <= 0:
            return None
        cost_pct = self.costs.round_trip_cost * 100
        hourly = gross / HOURS_PER_YEAR
        if hourly <= 0:
            return None
        return cost_pct / hourly

    @property
    def direction(self) -> str:
        """Which side collects. Long spot + short perp when funding is positive."""
        return "long spot / short perp" if self.funding.shorts_get_paid else "short spot / long perp"

    @property
    def is_viable(self) -> bool:
        """Whether this clears the bar for being worth running at all."""
        return bool(self.warnings() == [] and self.net_annualized_pct > 0)

    def warnings(self) -> list[str]:
        """Everything that should stop you putting this on."""
        out: list[str] = []

        if self.net_annualized_pct <= 0:
            out.append(
                f"negative after costs: {self.gross_annualized_pct:.2f}% gross becomes "
                f"{self.net_annualized_pct:.2f}% net"
            )

        breakeven = self.breakeven_hours
        if breakeven is not None and breakeven > self.max_breakeven_hours:
            out.append(
                f"takes {breakeven / 24:.1f} days just to cover fees, beyond the "
                f"{self.max_breakeven_hours / 24:.1f}-day limit you set"
            )

        if self.history:
            if self.history.intervals < 6:
                out.append(f"only {self.history.intervals} funding observations — too few to judge")
            elif self.history.positive_share < 0.7 and self.funding.shorts_get_paid:
                out.append(
                    f"funding favoured shorts only {self.history.positive_share:.0%} of intervals — "
                    f"it flips often"
                )
            if self.history.volatility > abs(self.history.mean_rate) and self.history.intervals >= 6:
                out.append("funding is more volatile than its own average — the carry is unreliable")

        if self.short_leg_requires_borrow:
            out.append("short spot leg needs borrow, which most retail accounts cannot do cheaply")

        return out

    @property
    def short_leg_requires_borrow(self) -> bool:
        """Negative funding means shorting spot, which is far harder than holding it."""
        return not self.funding.shorts_get_paid

    def as_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "venue": self.venue,
            "direction": self.direction,
            "funding_rate": self.funding.rate,
            "gross_annualized_pct": self.gross_annualized_pct,
            "net_annualized_pct": self.net_annualized_pct,
            "breakeven_hours": self.breakeven_hours,
            "max_breakeven_hours": self.max_breakeven_hours,
            "positive_share": self.history.positive_share if self.history else None,
            "intervals": self.history.intervals if self.history else 0,
            "viable": self.is_viable,
            "warnings": self.warnings(),
        }


@dataclass
class BasisPosition:
    """An open delta-neutral carry position."""

    symbol: str
    venue: str
    spot_amount: float
    perp_amount: float               # negative when short
    spot_entry: float
    perp_entry: float
    opened_at: datetime
    funding_collected: float = 0.0
    fees_paid: float = 0.0

    @property
    def net_delta(self) -> float:
        """Residual price exposure. Should sit near zero for a true carry trade."""
        return self.spot_amount + self.perp_amount

    def delta_drift_pct(self, price: float) -> float:
        """Net exposure as a share of gross position value."""
        gross = (abs(self.spot_amount) + abs(self.perp_amount)) * price
        return 0.0 if gross <= 0 else abs(self.net_delta) * price / gross * 100

    def pnl(self, spot_price: float, perp_price: float) -> float:
        """Total P&L: funding collected, plus the two legs, minus fees.

        The legs should roughly cancel; what is left is the carry.
        """
        spot_leg = (spot_price - self.spot_entry) * self.spot_amount
        perp_leg = (perp_price - self.perp_entry) * self.perp_amount
        return spot_leg + perp_leg + self.funding_collected - self.fees_paid

    def age_hours(self, now: datetime) -> float:
        return (now - self.opened_at).total_seconds() / 3600
