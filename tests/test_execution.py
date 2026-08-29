"""Execution economics — the thing that killed every strategy in the search."""

import pytest

from tradingbot.execution import (
    FEE_TIERS,
    ExecutionModel,
    FeeTier,
    Liquidity,
    breakeven_edge_per_trade,
    compare_execution,
    get_tier,
)


def test_fee_tiers_are_available_by_name():
    tier = get_tier("binance_perp")
    assert tier.maker < tier.taker


def test_an_unknown_tier_lists_the_known_ones():
    with pytest.raises(KeyError, match="unknown fee tier"):
        get_tier("not_a_venue")


def test_every_bundled_tier_has_maker_at_or_below_taker():
    for name, tier in FEE_TIERS.items():
        assert tier.maker <= tier.taker, f"{name} charges more to make than to take"


def test_rate_depends_on_which_side_of_the_book_you_were_on():
    tier = FeeTier("test", maker=0.0001, taker=0.0007)
    assert tier.rate_for(Liquidity.MAKER) == 0.0001
    assert tier.rate_for(Liquidity.TAKER) == 0.0007
    assert tier.maker_saving == pytest.approx(0.0006)


# ------------------------------------------------------------------ model
def test_taker_execution_pays_the_taker_fee():
    model = ExecutionModel(get_tier("binance_perp"), prefer_maker=False)
    assert model.effective_fee() == get_tier("binance_perp").taker


def test_maker_execution_blends_fills_and_misses():
    """A missed maker order becomes a taker order, and the cost must reflect that."""
    tier = FeeTier("test", maker=0.0, taker=0.001)
    model = ExecutionModel(tier, prefer_maker=True, maker_fill_rate=0.6)
    # 60% fill at 0, 40% swept at 0.001.
    assert model.effective_fee() == pytest.approx(0.0004)


def test_a_perfect_fill_rate_pays_only_the_maker_fee():
    tier = FeeTier("test", maker=0.0002, taker=0.001)
    model = ExecutionModel(tier, prefer_maker=True, maker_fill_rate=1.0)
    assert model.effective_fee() == pytest.approx(0.0002)


def test_a_zero_fill_rate_is_no_better_than_taking():
    tier = FeeTier("test", maker=0.0, taker=0.001)
    maker = ExecutionModel(tier, prefer_maker=True, maker_fill_rate=0.0)
    taker = ExecutionModel(tier, prefer_maker=False)
    assert maker.effective_fee() == taker.effective_fee()
    assert maker.round_trip_cost() == pytest.approx(taker.round_trip_cost())


def test_a_maker_rebate_produces_a_negative_fee():
    """Some venues pay you to provide liquidity; the arithmetic must allow it."""
    tier = FeeTier("rebate", maker=-0.0001, taker=0.0005)
    model = ExecutionModel(tier, prefer_maker=True, maker_fill_rate=1.0)
    assert model.effective_fee() < 0


def test_makers_earn_the_spread_rather_than_paying_it():
    tier = get_tier("binance_perp")
    taker = ExecutionModel(tier, prefer_maker=False, spread_pct=0.0004)
    maker = ExecutionModel(tier, prefer_maker=True, maker_fill_rate=1.0, spread_pct=0.0004)
    assert maker.effective_slippage() == 0.0
    assert taker.effective_slippage() == 0.0004


def test_maker_execution_saves_money_versus_taking():
    tier = get_tier("binance_perp")
    model = ExecutionModel(tier, prefer_maker=True, maker_fill_rate=0.8)
    assert model.saving_vs_taker() > 0


@pytest.mark.parametrize("bad", [-0.1, 1.1])
def test_an_impossible_fill_rate_is_rejected(bad):
    with pytest.raises(ValueError, match="maker_fill_rate"):
        ExecutionModel(get_tier("binance"), prefer_maker=True, maker_fill_rate=bad)


def test_negative_spread_is_rejected():
    with pytest.raises(ValueError, match="spread_pct"):
        ExecutionModel(get_tier("binance"), spread_pct=-0.001)


# -------------------------------------------------------------- breakeven
def test_breakeven_is_the_full_round_trip():
    model = ExecutionModel(FeeTier("t", 0.001, 0.001), prefer_maker=False, spread_pct=0.0)
    assert breakeven_edge_per_trade(model) == pytest.approx(0.2)  # 0.1% each way


def test_an_expensive_venue_demands_a_much_larger_edge():
    """Coinbase's taker fee needs an order of magnitude more edge than a perp venue."""
    cheap = breakeven_edge_per_trade(ExecutionModel(get_tier("binance_perp")))
    dear = breakeven_edge_per_trade(ExecutionModel(get_tier("coinbase")))
    assert dear > cheap * 5


def test_the_comparison_table_covers_taker_and_every_fill_rate():
    rows = compare_execution(get_tier("binance_perp"), [0.5, 1.0])
    assert rows[0]["mode"] == "taker"
    assert len(rows) == 3
    # Better fill rates must never cost more.
    maker_rows = [r for r in rows if r["mode"] == "maker"]
    assert maker_rows[0]["round_trip"] >= maker_rows[-1]["round_trip"]


# ----------------------------------------------------------------- config
def test_a_fee_tier_in_config_sets_the_modelled_costs():
    from tradingbot.config import from_dict

    config = from_dict({"execution": {"fee_tier": "binance_perp", "prefer_maker": True,
                                      "maker_fill_rate": 0.8}})
    model = config.execution.execution_model()
    assert config.execution.fee_rate == pytest.approx(model.effective_fee())
    assert config.execution.slippage_pct == pytest.approx(model.effective_slippage())


def test_no_fee_tier_leaves_the_explicit_rates_alone():
    from tradingbot.config import from_dict

    config = from_dict({"execution": {"fee_rate": 0.002, "slippage_pct": 0.001}})
    assert config.execution.fee_rate == 0.002
    assert config.execution.execution_model() is None


def test_an_unknown_fee_tier_is_rejected():
    from tradingbot.config import ConfigError, from_dict

    with pytest.raises(ConfigError, match="fee_tier"):
        from_dict({"execution": {"fee_tier": "moon_exchange"}})


def test_an_impossible_fill_rate_is_rejected_in_config():
    from tradingbot.config import ConfigError, from_dict

    with pytest.raises(ConfigError, match="maker_fill_rate"):
        from_dict({"execution": {"maker_fill_rate": 2.0}})


def test_cheaper_execution_improves_a_backtest(config):
    """The whole point: modelled maker execution must show up in the results."""
    from tradingbot.backtest import Backtester
    from tradingbot.data import generate_synthetic
    from tradingbot.strategies import get_strategy

    candles = generate_synthetic(bars=1500, seed=12)
    strategy = get_strategy("sma_cross", fast_period=10, slow_period=30)

    config.execution.fee_rate = 0.001
    expensive = Backtester(config, strategy).run("BTC/USDT", candles)
    config.execution.fee_rate = 0.0002
    cheap = Backtester(config, strategy).run("BTC/USDT", candles)

    assert cheap.metrics.total_fees < expensive.metrics.total_fees
    assert cheap.metrics.total_return_pct > expensive.metrics.total_return_pct
