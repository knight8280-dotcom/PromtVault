"""Rank funding-carry opportunities, net of what it costs to run them.

The scanner's job is to be pessimistic. A venue's headline funding rate is a
gross number over eight hours; what matters is what survives fees, how reliably
the rate has persisted, and how long you must stay in to break even.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .models import CarryCosts, CarryOpportunity, FundingHistory
from .sources import FundingSource, FundingSourceError

log = logging.getLogger(__name__)


@dataclass
class ScanResult:
    opportunities: list[CarryOpportunity] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    scanned: int = 0

    @property
    def viable(self) -> list[CarryOpportunity]:
        """Only those that clear every check, best net carry first."""
        return sorted(
            (o for o in self.opportunities if o.is_viable),
            key=lambda o: o.net_annualized_pct,
            reverse=True,
        )

    @property
    def ranked(self) -> list[CarryOpportunity]:
        """Everything scanned, best net carry first, viable or not."""
        return sorted(self.opportunities, key=lambda o: o.net_annualized_pct, reverse=True)

    def as_dict(self) -> dict:
        return {
            "scanned": self.scanned,
            "viable_count": len(self.viable),
            "opportunities": [o.as_dict() for o in self.ranked],
            "errors": self.errors,
        }


class CarryScanner:
    """Scores perpetual funding across symbols on one venue."""

    def __init__(
        self,
        source: FundingSource,
        costs: CarryCosts | None = None,
        *,
        history_limit: int = 30,
        min_intervals: int = 6,
    ) -> None:
        self.source = source
        self.costs = costs or CarryCosts()
        self.history_limit = history_limit
        self.min_intervals = min_intervals

    def scan(self, symbols: list[str]) -> ScanResult:
        """Score each symbol. One failure never stops the scan."""
        result = ScanResult()

        for symbol in symbols:
            result.scanned += 1
            try:
                current = self.source.current(symbol)
            except FundingSourceError as exc:
                result.errors.append(str(exc))
                continue

            history: FundingHistory | None = None
            try:
                history = self.source.history(symbol, limit=self.history_limit)
            except FundingSourceError as exc:
                # A missing history is survivable; the report says the sample is thin.
                log.debug("no funding history for %s: %s", symbol, exc)
                result.errors.append(f"no history for {symbol}: {exc}")

            result.opportunities.append(
                CarryOpportunity(
                    symbol=symbol,
                    venue=getattr(self.source, "venue", "unknown"),
                    funding=current,
                    history=history,
                    costs=self.costs,
                )
            )

        return result

    def scan_all(self, limit: int = 25) -> ScanResult:
        """Scan the venue's most prominent perpetuals."""
        try:
            symbols = self.source.perpetual_symbols()[:limit]
        except FundingSourceError as exc:
            return ScanResult(errors=[str(exc)])
        return self.scan(symbols)


def format_scan(result: ScanResult, costs: CarryCosts) -> str:
    """Render a scan as a plain-text report."""
    lines = [
        "",
        "  Funding carry scan",
        f"  {'=' * 76}",
        f"  Costs assumed: spot {costs.spot_fee:.4%} + perp {costs.perp_fee:.4%} per side, "
        f"slippage {costs.slippage_pct:.4%}",
        f"  Round trip: {costs.round_trip_cost:.3%} of position value",
        "",
        f"  {'symbol':<22}{'gross APR':>11}{'net APR':>10}{'breakeven':>12}{'stable':>9}  status",
        f"  {'-' * 76}",
    ]

    if not result.opportunities:
        lines += ["  nothing scanned", ""]
        return "\n".join(lines)

    for o in result.ranked:
        breakeven = o.breakeven_hours
        be = f"{breakeven / 24:.1f}d" if breakeven is not None else "never"
        stable = f"{o.history.positive_share:.0%}" if o.history else "n/a"
        status = "VIABLE" if o.is_viable else (o.warnings()[0][:34] if o.warnings() else "")
        lines.append(
            f"  {o.symbol[:21]:<22}{o.gross_annualized_pct:>10.2f}%"
            f"{o.net_annualized_pct:>9.2f}%{be:>12}{stable:>9}  {status}"
        )

    viable = result.viable
    lines += ["", f"  {len(viable)} of {result.scanned} clear every check."]
    if viable:
        best = viable[0]
        lines += [
            "",
            f"  Best: {best.symbol} on {best.venue}",
            f"    {best.direction}",
            f"    {best.net_annualized_pct:.2f}% APR net of fees, breaks even after "
            f"{(best.breakeven_hours or 0) / 24:.1f} days",
        ]
    else:
        lines.append("  Nothing here is worth running at these costs.")

    lines += [
        "",
        "  Carry is real but not free money. It pays you for holding balance sheet and",
        "  wearing the risks: funding can flip, the perp leg can be liquidated in a fast",
        "  move, and the whole position depends on the venue staying solvent.",
        "",
    ]
    if result.errors:
        lines += ["  Incomplete data:"] + [f"    - {e}" for e in result.errors[:5]] + [""]
    return "\n".join(lines)
