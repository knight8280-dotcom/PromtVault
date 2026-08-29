"""Loading, caching and generating candles."""

from datetime import datetime, timedelta, timezone

import pytest

from tradingbot.data import csv_store, generate_synthetic, load_history, timeframe_delta
from tradingbot.models import Candle

NOW = datetime(2024, 1, 1, tzinfo=timezone.utc)


def sample(count=5):
    return [
        Candle(NOW + timedelta(hours=i), 100 + i, 102 + i, 99 + i, 101 + i, 10.0)
        for i in range(count)
    ]


# ------------------------------------------------------------- csv_store
def test_candles_round_trip_through_csv(tmp_path):
    path = csv_store.save(tmp_path / "out.csv", sample())
    loaded = csv_store.load(path)
    assert len(loaded) == 5
    assert loaded[0].timestamp == NOW
    assert loaded[0].close == 101


def test_a_cache_path_is_filesystem_safe():
    path = csv_store.cache_path("data", "BTC/USDT", "1h")
    assert "/" not in path.name
    assert path.name == "BTC-USDT_1h.csv"


def test_iso_timestamps_are_accepted(tmp_path):
    path = tmp_path / "iso.csv"
    path.write_text(
        "timestamp,open,high,low,close,volume\n"
        "2024-01-01T00:00:00Z,100,102,99,101,10\n"
        "2024-01-01T01:00:00Z,101,103,100,102,11\n"
    )
    loaded = csv_store.load(path)
    assert loaded[0].timestamp == NOW
    assert loaded[1].close == 102


def test_second_and_millisecond_timestamps_are_both_understood(tmp_path):
    path = tmp_path / "epoch.csv"
    path.write_text(
        "timestamp,open,high,low,close,volume\n"
        "1704067200,100,102,99,101,10\n"          # seconds
        "1704070800000,101,103,100,102,11\n"      # milliseconds
    )
    loaded = csv_store.load(path)
    assert loaded[0].timestamp == NOW
    assert loaded[1].timestamp == NOW + timedelta(hours=1)


def test_candles_are_sorted_oldest_first(tmp_path):
    path = tmp_path / "shuffled.csv"
    rows = "\n".join(
        f"{int((NOW + timedelta(hours=i)).timestamp() * 1000)},1,1,1,{i},1"
        for i in (3, 1, 4, 0, 2)
    )
    path.write_text("timestamp,open,high,low,close,volume\n" + rows + "\n")
    loaded = csv_store.load(path)
    assert [c.timestamp for c in loaded] == sorted(c.timestamp for c in loaded)


def test_a_missing_column_is_reported(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("timestamp,open,high,low\n1704067200000,1,2,3\n")
    with pytest.raises(ValueError, match="missing column"):
        csv_store.load(path)


def test_a_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        csv_store.load(tmp_path / "nope.csv")


def test_merging_deduplicates_by_timestamp_with_fresh_data_winning():
    old = sample(3)
    newer = [Candle(old[2].timestamp, 1, 1, 1, 999.0, 1)]
    merged = csv_store.merge(old, newer)
    assert len(merged) == 3
    assert merged[-1].close == 999.0


def test_merging_keeps_chronological_order():
    merged = csv_store.merge(sample(3)[2:], sample(3)[:2])
    assert [c.timestamp for c in merged] == sorted(c.timestamp for c in merged)


# ---------------------------------------------------------------- feed
def test_load_history_prefers_an_explicit_csv(tmp_path):
    path = csv_store.save(tmp_path / "explicit.csv", sample())
    assert len(load_history("BTC/USDT", "1h", csv_path=str(path))) == 5


def test_load_history_reads_the_cache(tmp_path):
    csv_store.save(csv_store.cache_path(tmp_path, "BTC/USDT", "1h"), sample())
    assert len(load_history("BTC/USDT", "1h", data_dir=str(tmp_path))) == 5


def test_load_history_without_data_explains_the_options(tmp_path):
    with pytest.raises(FileNotFoundError, match="--synthetic"):
        load_history("BTC/USDT", "1h", data_dir=str(tmp_path))


@pytest.mark.parametrize("timeframe,minutes", [("1m", 1), ("1h", 60), ("4h", 240), ("1d", 1440)])
def test_timeframe_deltas(timeframe, minutes):
    assert timeframe_delta(timeframe) == timedelta(minutes=minutes)


def test_an_unknown_timeframe_is_rejected():
    with pytest.raises(ValueError, match="unsupported timeframe"):
        timeframe_delta("7h")


# ----------------------------------------------------------- synthetic
def test_synthetic_data_is_reproducible_for_a_seed():
    a = generate_synthetic(bars=200, seed=42)
    b = generate_synthetic(bars=200, seed=42)
    assert [c.close for c in a] == [c.close for c in b]


def test_different_seeds_give_different_data():
    a = generate_synthetic(bars=200, seed=1)
    b = generate_synthetic(bars=200, seed=2)
    assert [c.close for c in a] != [c.close for c in b]


def test_synthetic_candles_are_internally_consistent():
    for c in generate_synthetic(bars=500, seed=3):
        assert c.low <= c.open <= c.high
        assert c.low <= c.close <= c.high
        assert c.low > 0 and c.volume >= 0


def test_synthetic_candles_are_evenly_spaced():
    candles = generate_synthetic(bars=50, timeframe="4h", seed=1)
    gaps = {candles[i + 1].timestamp - candles[i].timestamp for i in range(len(candles) - 1)}
    assert gaps == {timedelta(hours=4)}
