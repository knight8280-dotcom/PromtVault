"""Funding carry: the arithmetic, and the honesty about what eats it."""

from datetime import datetime, timedelta, timezone

import pytest

from tradingbot.carry import (
    BasisPosition,
    CarryCosts,
    CarryOpportunity,
    CarryScanner,
    FundingHistory,
    FundingRate,
    FundingSourceError,
    format_scan,
)
from tradingbot.carry.models import HOURS_PER_YEAR
from tradingbot.carry.sources import FundingSource

NOW = datetime(2024, 1, 1, tzinfo=timezone.utc)


def rate(value=0.0001, hours=8, symbol="BTC/USDT:USDT", when=None):
    return FundingRate(symbol, "binance", value, when or NOW, interval_hours=hours)


def history(values, symbol="BTC/USDT:USDT"):
    return FundingHistory(symbol, "binance", [
        rate(v, when=NOW + timedelta(hours=8 * i)) for i, v in enumerate(values)
    ])


# ------------------------------------------------------------ annualising
def test_a_funding_rate_annualises_over_its_interval():
    # 1bp every 8h = 3 payments a day = 1095 a year.
    assert rate(0.0001, hours=8).annualized_pct == pytest.approx(0.0001 * 1095 * 100)


def test_a_shorter_interval_annualises_higher():
    """Getting the interval wrong scales every APR in the report, so it must be read."""
    assert rate(0.0001, hours=1).annualized_pct == pytest.approx(
        rate(0.0001, hours=8).annualized_pct * 8
    )


def test_positive_funding_means_shorts_get_paid():
    assert rate(0.0001).shorts_get_paid
    assert not rate(-0.0001).shorts_get_paid


def test_basis_is_the_gap_between_mark_and_index():
    r = FundingRate("BTC", "binance", 0.0001, NOW, mark_price=101.0, index_price=100.0)
    assert r.basis_pct == pytest.approx(1.0)
    assert rate().basis_pct is None


# -------------------------------------------------------------- stability
def test_history_summarises_consistency_not_just_average():
    h = history([0.0001] * 10)
    assert h.positive_share == 1.0
    assert h.volatility == pytest.approx(0.0)
    assert h.intervals == 10


def test_a_flipping_rate_shows_a_low_positive_share():
    h = history([0.0003, -0.0003] * 5)
    assert h.positive_share == pytest.approx(0.5)
    assert h.mean_rate == pytest.approx(0.0, abs=1e-12)


def test_the_worst_interval_is_reported():
    assert history([0.0002, -0.0005, 0.0001]).worst_rate == -0.0005


# ------------------------------------------------------------------ costs
def test_round_trip_cost_covers_both_legs_both_ways():
    costs = CarryCosts(spot_fee=0.001, perp_fee=0.0005, slippage_pct=0.0002)
    # (spot + perp + 2 slippage) each way, twice.
    assert costs.round_trip_cost == pytest.approx((0.001 + 0.0005 + 0.0004) * 2)


def test_carry_net_of_costs_is_lower_than_gross():
    o = CarryOpportunity("BTC", "binance", rate(0.0002), costs=CarryCosts())
    assert o.net_annualized_pct < o.gross_annualized_pct


def test_cheaper_execution_leaves_more_carry():
    dear = CarryOpportunity("BTC", "binance", rate(0.0002),
                            costs=CarryCosts(spot_fee=0.001, perp_fee=0.0005))
    cheap = CarryOpportunity("BTC", "binance", rate(0.0002),
                             costs=CarryCosts(spot_fee=0.0002, perp_fee=0.0002))
    assert cheap.net_annualized_pct > dear.net_annualized_pct
    assert cheap.breakeven_hours < dear.breakeven_hours


def test_history_is_preferred_over_a_single_print():
    """One observation is noise; you are underwriting the next few days."""
    spike = CarryOpportunity("BTC", "binance", rate(0.001), history=history([0.00001] * 10))
    assert spike.gross_annualized_pct == pytest.approx(abs(spike.history.mean_annualized_pct))
    assert spike.gross_annualized_pct < rate(0.001).annualized_pct


def test_a_thin_history_falls_back_to_the_current_rate():
    o = CarryOpportunity("BTC", "binance", rate(0.0002), history=history([0.0002]))
    assert o.gross_annualized_pct == pytest.approx(rate(0.0002).annualized_pct)


def test_breakeven_is_the_time_needed_to_cover_the_round_trip():
    costs = CarryCosts(spot_fee=0.001, perp_fee=0.0005, slippage_pct=0.0)
    o = CarryOpportunity("BTC", "binance", rate(0.0001), costs=costs)
    hourly = o.gross_annualized_pct / HOURS_PER_YEAR
    assert o.breakeven_hours == pytest.approx(costs.round_trip_cost * 100 / hourly)


def test_a_shorter_hold_is_punished_by_the_round_trip():
    o = CarryOpportunity("BTC", "binance", rate(0.0003), costs=CarryCosts())
    assert o.net_annualized_for(24) < o.net_annualized_for(HOURS_PER_YEAR)


def test_zero_funding_has_no_breakeven():
    assert CarryOpportunity("BTC", "binance", rate(0.0)).breakeven_hours is None


# --------------------------------------------------------------- warnings
def test_a_slow_breakeven_is_flagged():
    o = CarryOpportunity("BTC", "binance", rate(0.00001),
                         history=history([0.00001] * 10), costs=CarryCosts())
    assert any("cover fees" in w for w in o.warnings())
    assert not o.is_viable


def test_the_breakeven_limit_is_relative_to_your_holding_period():
    """3 days to cover fees is fine for a multi-week carry and fatal for an overnight one."""
    cheap = CarryCosts(spot_fee=0.0002, perp_fee=0.0002, slippage_pct=0.0001)
    common = dict(history=history([0.0003] * 20), costs=cheap)

    patient = CarryOpportunity("BTC", "binance", rate(0.0003),
                               max_breakeven_hours=7 * 24, **common)
    impatient = CarryOpportunity("BTC", "binance", rate(0.0003),
                                 max_breakeven_hours=24, **common)

    assert patient.breakeven_hours == impatient.breakeven_hours  # same trade
    assert patient.is_viable                                     # different appetite
    assert not impatient.is_viable
    assert "limit you set" in impatient.warnings()[0]


def test_a_realistic_carry_at_maker_fees_is_viable():
    """3bp funding at maker fees is ~33% APR; the tool must not reject it out of hand."""
    o = CarryOpportunity(
        "BTC", "binance", rate(0.0003), history=history([0.0003] * 20),
        costs=CarryCosts(spot_fee=0.0004, perp_fee=0.00026, slippage_pct=0.0001),
    )
    assert o.net_annualized_pct > 25
    assert o.is_viable, o.warnings()


def test_flipping_funding_is_flagged():
    o = CarryOpportunity("BTC", "binance", rate(0.0005), history=history([0.0005, -0.0005] * 5))
    assert any("flips often" in w or "volatile" in w for w in o.warnings())


def test_too_few_observations_is_flagged():
    o = CarryOpportunity("BTC", "binance", rate(0.0005), history=history([0.0005] * 3))
    assert any("too few" in w for w in o.warnings())


def test_negative_funding_flags_the_borrow_problem():
    """Collecting negative funding means shorting spot, which retail mostly cannot."""
    o = CarryOpportunity("BTC", "binance", rate(-0.0005), history=history([-0.0005] * 10))
    assert o.short_leg_requires_borrow
    assert any("borrow" in w for w in o.warnings())
    assert not o.is_viable


def test_a_strong_consistent_carry_is_viable():
    o = CarryOpportunity(
        "BTC", "binance", rate(0.0005), history=history([0.0005] * 20),
        costs=CarryCosts(spot_fee=0.0002, perp_fee=0.0002, slippage_pct=0.0001),
    )
    assert o.warnings() == []
    assert o.is_viable
    assert o.direction == "long spot / short perp"


def test_an_opportunity_serialises_for_reporting():
    payload = CarryOpportunity("BTC", "binance", rate(0.0005), history=history([0.0005] * 10)).as_dict()
    assert {"symbol", "net_annualized_pct", "breakeven_hours", "viable", "warnings"} <= set(payload)


# ------------------------------------------------------------- positions
def test_a_balanced_basis_position_is_delta_neutral():
    p = BasisPosition("BTC", "binance", spot_amount=1.0, perp_amount=-1.0,
                      spot_entry=100.0, perp_entry=100.0, opened_at=NOW)
    assert p.net_delta == 0.0
    assert p.delta_drift_pct(100.0) == 0.0


def test_price_moves_cancel_between_the_legs():
    p = BasisPosition("BTC", "binance", 1.0, -1.0, 100.0, 100.0, NOW)
    p.funding_collected = 5.0
    # Price doubles: the spot gain and perp loss offset, leaving the carry.
    assert p.pnl(200.0, 200.0) == pytest.approx(5.0)
    assert p.pnl(50.0, 50.0) == pytest.approx(5.0)


def test_fees_reduce_the_carry_collected():
    p = BasisPosition("BTC", "binance", 1.0, -1.0, 100.0, 100.0, NOW,
                      funding_collected=5.0, fees_paid=2.0)
    assert p.pnl(100.0, 100.0) == pytest.approx(3.0)


def test_an_unbalanced_position_reports_its_drift():
    p = BasisPosition("BTC", "binance", 1.0, -0.9, 100.0, 100.0, NOW)
    assert p.net_delta == pytest.approx(0.1)
    assert p.delta_drift_pct(100.0) > 0


# ----------------------------------------------------------------- scanner
class FakeFunding(FundingSource):
    def __init__(self, rates: dict, histories: dict | None = None, fail: set | None = None):
        self.rates = rates
        self.histories = histories or {}
        self.fail = fail or set()
        self.venue = "fake"

    def current(self, symbol):
        if symbol in self.fail:
            raise FundingSourceError(f"no data for {symbol}")
        return self.rates[symbol]

    def history(self, symbol, limit=30):
        if symbol not in self.histories:
            raise FundingSourceError(f"no history for {symbol}")
        return self.histories[symbol]

    def perpetual_symbols(self):
        return sorted(self.rates)


def test_the_scanner_ranks_by_net_carry():
    source = FakeFunding(
        {"A": rate(0.0002, symbol="A"), "B": rate(0.0008, symbol="B")},
        {"A": history([0.0002] * 10), "B": history([0.0008] * 10)},
    )
    result = CarryScanner(source, CarryCosts(spot_fee=0.0002, perp_fee=0.0002)).scan(["A", "B"])
    assert [o.symbol for o in result.ranked] == ["B", "A"]
    assert result.scanned == 2


def test_the_scanner_separates_viable_from_merely_positive():
    source = FakeFunding(
        {"GOOD": rate(0.0008, symbol="GOOD"), "FLIPPY": rate(0.0008, symbol="FLIPPY")},
        {"GOOD": history([0.0008] * 20), "FLIPPY": history([0.0008, -0.0008] * 10)},
    )
    result = CarryScanner(source, CarryCosts(spot_fee=0.0002, perp_fee=0.0002)).scan(["GOOD", "FLIPPY"])
    assert [o.symbol for o in result.viable] == ["GOOD"]


def test_one_failing_symbol_does_not_stop_the_scan():
    source = FakeFunding({"A": rate(0.0002, symbol="A")}, {"A": history([0.0002] * 10)},
                         fail={"BROKEN"})
    result = CarryScanner(source).scan(["A", "BROKEN"])
    assert len(result.opportunities) == 1
    assert result.errors


def test_a_missing_history_is_survivable():
    source = FakeFunding({"A": rate(0.0002, symbol="A")})
    result = CarryScanner(source).scan(["A"])
    assert len(result.opportunities) == 1
    assert result.opportunities[0].history is None


def test_the_report_states_the_risks():
    source = FakeFunding({"A": rate(0.0008, symbol="A")}, {"A": history([0.0008] * 20)})
    costs = CarryCosts(spot_fee=0.0002, perp_fee=0.0002)
    report = format_scan(CarryScanner(source, costs).scan(["A"]), costs)
    assert "not free money" in report
    assert "liquidated" in report
    assert "Round trip" in report


def test_an_empty_scan_reports_cleanly():
    report = format_scan(CarryScanner(FakeFunding({})).scan([]), CarryCosts())
    assert "nothing scanned" in report
