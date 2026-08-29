"""Performance statistics for a completed run."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

from .models import EquityPoint, Trade

# Bars per year, used to annualise returns for each supported timeframe.
PERIODS_PER_YEAR = {
    "1m": 525_600,
    "3m": 175_200,
    "5m": 105_120,
    "15m": 35_040,
    "30m": 17_520,
    "1h": 8_760,
    "2h": 4_380,
    "4h": 2_190,
    "6h": 1_460,
    "12h": 730,
    "1d": 365,
}


@dataclass
class Metrics:
    starting_equity: float = 0.0
    ending_equity: float = 0.0
    total_return_pct: float = 0.0
    annualized_return_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_duration: int = 0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    volatility_pct: float = 0.0

    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    total_fees: float = 0.0
    exposure_pct: float = 0.0

    start: datetime | None = None
    end: datetime | None = None
    exit_reasons: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict:
        out = {}
        for key, value in self.__dict__.items():
            out[key] = value.isoformat() if isinstance(value, datetime) else value
        return out


def max_drawdown(equity: list[float]) -> tuple[float, int]:
    """Return (max drawdown as a fraction, longest underwater run in points)."""
    if not equity:
        return 0.0, 0
    peak = equity[0]
    worst = 0.0
    underwater = longest = 0
    for value in equity:
        if value >= peak:
            peak = value
            underwater = 0
        else:
            underwater += 1
            longest = max(longest, underwater)
        if peak > 0:
            worst = max(worst, (peak - value) / peak)
    return worst, longest


def _returns(equity: list[float]) -> list[float]:
    return [
        (equity[i] - equity[i - 1]) / equity[i - 1]
        for i in range(1, len(equity))
        if equity[i - 1] > 0
    ]


def sharpe(returns: list[float], periods_per_year: int, risk_free: float = 0.0) -> float:
    """Annualised Sharpe ratio of a series of per-bar returns."""
    if len(returns) < 2:
        return 0.0
    excess = [r - risk_free / periods_per_year for r in returns]
    mean = sum(excess) / len(excess)
    variance = sum((r - mean) ** 2 for r in excess) / (len(excess) - 1)
    sd = math.sqrt(variance)
    # Guard against float noise: a constant series has no risk to adjust for, and
    # an exact `sd == 0` check lets 1e-18 through and produces an absurd ratio.
    if sd < 1e-12:
        return 0.0
    return (mean / sd) * math.sqrt(periods_per_year)


def sortino(returns: list[float], periods_per_year: int) -> float:
    """Like Sharpe, but only downside deviation counts as risk."""
    if len(returns) < 2:
        return 0.0
    mean = sum(returns) / len(returns)
    downside = [r for r in returns if r < 0]
    if not downside:
        return 0.0
    dd = math.sqrt(sum(r**2 for r in downside) / len(returns))
    if dd < 1e-12:
        return 0.0
    return (mean / dd) * math.sqrt(periods_per_year)


def compute(
    equity_curve: list[EquityPoint],
    trades: list[Trade],
    timeframe: str = "1h",
    bars_in_market: int = 0,
) -> Metrics:
    """Summarise a run's equity curve and trade list."""
    m = Metrics()
    if not equity_curve:
        return m

    values = [p.equity for p in equity_curve]
    m.starting_equity = values[0]
    m.ending_equity = values[-1]
    m.start = equity_curve[0].timestamp
    m.end = equity_curve[-1].timestamp
    if m.starting_equity > 0:
        m.total_return_pct = (m.ending_equity / m.starting_equity - 1) * 100

    m.max_drawdown_pct, m.max_drawdown_duration = max_drawdown(values)
    m.max_drawdown_pct *= 100

    periods = PERIODS_PER_YEAR.get(timeframe, 8_760)
    rets = _returns(values)
    m.sharpe_ratio = sharpe(rets, periods)
    m.sortino_ratio = sortino(rets, periods)

    if len(rets) >= 2:
        mean = sum(rets) / len(rets)
        variance = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
        m.volatility_pct = math.sqrt(variance) * math.sqrt(periods) * 100

    # Annualise the realised return over the actual elapsed bars.
    if len(values) > 1 and m.starting_equity > 0 and m.ending_equity > 0:
        years = (len(values) - 1) / periods
        if years > 0:
            m.annualized_return_pct = ((m.ending_equity / m.starting_equity) ** (1 / years) - 1) * 100
    if m.max_drawdown_pct > 0:
        m.calmar_ratio = m.annualized_return_pct / m.max_drawdown_pct

    if bars_in_market and len(values) > 0:
        m.exposure_pct = 100 * bars_in_market / len(values)

    _summarise_trades(m, trades)
    return m


def _summarise_trades(m: Metrics, trades: list[Trade]) -> None:
    m.total_trades = len(trades)
    if not trades:
        return

    wins = [t for t in trades if t.is_win]
    losses = [t for t in trades if not t.is_win]
    m.winning_trades = len(wins)
    m.losing_trades = len(losses)
    m.win_rate = 100 * len(wins) / len(trades)

    gross_profit = sum(t.net_pnl for t in wins)
    gross_loss = abs(sum(t.net_pnl for t in losses))
    m.profit_factor = gross_profit / gross_loss if gross_loss else (math.inf if gross_profit else 0.0)

    m.avg_win = gross_profit / len(wins) if wins else 0.0
    m.avg_loss = -gross_loss / len(losses) if losses else 0.0
    m.expectancy = sum(t.net_pnl for t in trades) / len(trades)
    m.largest_win = max((t.net_pnl for t in trades), default=0.0)
    m.largest_loss = min((t.net_pnl for t in trades), default=0.0)
    m.total_fees = sum(t.fees for t in trades)

    for trade in trades:
        reason = trade.reason or "signal"
        m.exit_reasons[reason] = m.exit_reasons.get(reason, 0) + 1


def format_report(m: Metrics, title: str = "Results") -> str:
    """Render metrics as a plain-text report."""
    pf = "inf" if m.profit_factor == math.inf else f"{m.profit_factor:.2f}"
    period = ""
    if m.start and m.end:
        period = f"{m.start:%Y-%m-%d} to {m.end:%Y-%m-%d}"

    lines = [
        "",
        f"  {title}",
        f"  {'=' * max(len(title), 44)}",
        f"  Period                {period}",
        f"  Starting equity       {m.starting_equity:>14,.2f}",
        f"  Ending equity         {m.ending_equity:>14,.2f}",
        f"  Total return          {m.total_return_pct:>13.2f}%",
        f"  Annualized return     {m.annualized_return_pct:>13.2f}%",
        f"  Max drawdown          {m.max_drawdown_pct:>13.2f}%",
        f"  Volatility (ann.)     {m.volatility_pct:>13.2f}%",
        f"  Sharpe ratio          {m.sharpe_ratio:>14.2f}",
        f"  Sortino ratio         {m.sortino_ratio:>14.2f}",
        f"  Calmar ratio          {m.calmar_ratio:>14.2f}",
        f"  Time in market        {m.exposure_pct:>13.2f}%",
        "",
        f"  Trades                {m.total_trades:>14,}",
        f"  Win rate              {m.win_rate:>13.2f}%  ({m.winning_trades}W / {m.losing_trades}L)",
        f"  Profit factor         {pf:>14}",
        f"  Expectancy per trade  {m.expectancy:>14,.2f}",
        f"  Average win / loss    {m.avg_win:>14,.2f} / {m.avg_loss:,.2f}",
        f"  Largest win / loss    {m.largest_win:>14,.2f} / {m.largest_loss:,.2f}",
        f"  Fees paid             {m.total_fees:>14,.2f}",
    ]
    if m.exit_reasons:
        breakdown = ", ".join(f"{k}: {v}" for k, v in sorted(m.exit_reasons.items()))
        lines.append(f"  Exit reasons          {breakdown}")
    lines.append("")
    return "\n".join(lines)
