"""Unit tests for prepare_data.py's day-ordering fix and derived columns."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pandas as pd
import pytest

import prepare_data

CLEANED_DIR = os.path.join(ROOT, "cleaned")


def test_day_map_reverses_the_three_raw_labels():
    assert prepare_data.DAY_MAP == {0: 2, 1: 1, 2: 0}


def test_fix_day_remaps_every_row_with_no_leftover_raw_labels():
    raw = pd.DataFrame({"day": [0, 0, 1, 2, 2]})
    fixed = prepare_data.fix_day(raw)
    assert list(fixed["day"]) == [2, 2, 1, 0, 0]


def test_add_price_stats_matches_the_hand_computed_microprice_and_imbalance():
    raw = pd.DataFrame([{
        "day": 0, "timestamp": 200,
        "bid_price_1": 9994.0, "bid_volume_1": 13.0,
        "ask_price_1": 10013.0, "ask_volume_1": 21.0,
    }])
    stats = prepare_data.add_price_stats(raw)
    row = stats.iloc[0]
    assert row["spread"] == 19.0
    assert row["microprice"] == pytest.approx(10001.264705882353)
    assert row["imbalance"] == pytest.approx(-0.23529411764705882)
    assert row["globalTs"] == 0 * prepare_data.DAY_OFFSET + 200


def test_add_price_stats_leaves_spread_and_microprice_nan_when_one_side_is_missing():
    raw = pd.DataFrame([{
        "day": 0, "timestamp": 0,
        "bid_price_1": float("nan"), "bid_volume_1": float("nan"),
        "ask_price_1": 10013.0, "ask_volume_1": 30.0,
    }])
    stats = prepare_data.add_price_stats(raw)
    row = stats.iloc[0]
    assert pd.isna(row["spread"])
    assert pd.isna(row["microprice"])
    assert pd.isna(row["imbalance"])


@pytest.mark.skipif(not os.path.exists(os.path.join(CLEANED_DIR, "pepperPrices.csv")),
                     reason="cleaned/pepperPrices.csv not generated")
def test_prepared_pepper_global_timestamp_is_monotone_increasing():
    prices = pd.read_csv(os.path.join(CLEANED_DIR, "pepperPrices.csv"))
    assert prices["globalTs"].is_monotonic_increasing


@pytest.mark.skipif(not os.path.exists(os.path.join(CLEANED_DIR, "pepperPrices.csv")),
                     reason="cleaned/pepperPrices.csv not generated")
def test_prepared_pepper_mean_mid_price_increases_day_over_day():
    # Pepper trends up roughly 1000/day; this is the empirical check that
    # motivated the day fix in the first place (see prepare_data.py docstring).
    prices = pd.read_csv(os.path.join(CLEANED_DIR, "pepperPrices.csv"))
    meanByDay = prices[prices["mid_price"] > 0].groupby("day")["mid_price"].mean()
    assert list(meanByDay.index) == [0, 1, 2]
    assert meanByDay[0] < meanByDay[1] < meanByDay[2]
