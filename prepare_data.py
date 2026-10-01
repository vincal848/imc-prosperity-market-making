"""Regenerates cleaned/ from cleaned/raw/, fixing the reversed day labels.

The script that originally produced cleaned/*.csv is lost (see
commit 0be887b, "Fixed Day col issue, added metrics in analysis, and unified
data csv", which replaced the CSVs wholesale with no script attached). The
day column it wrote runs 0, 1, 2 but is backwards: INTARIAN_PEPPER_ROOT rises
roughly 1000 XIRECS per day across the round (confirmed by
Background_and_Research/PepperGraph.png, which shows three separate rising
sawtooth segments instead of one continuous line), and in the raw data:

    raw day 0 -> Pepper mid in [12000, 13000]  (latest, highest)
    raw day 1 -> Pepper mid in [11000, 12000]  (middle)
    raw day 2 -> Pepper mid in [10000, 11000]  (earliest, lowest)

so the chronological order is raw day 2, then 1, then 0 -- exactly reversed.
This matches IMC's own day-labeling convention for Prosperity round data
(files are named day -2, -1, 0, with 0 the most recent); whoever concatenated
the three source files most likely zipped them with range(3) instead of the
original negative labels and never reversed the result.

This script treats cleaned/raw/allPrices.csv and cleaned/raw/allTrades.csv
(verbatim copies of the pre-fix files) as the frozen source of truth, and
regenerates everything else in cleaned/ from them:

    day column remapped 0->2, 1->1, 2->0 (DAY_MAP below)
    globalTs = day * 1_000_000 + timestamp, monotonically increasing across
        the whole round (max intraday timestamp is 999900)
    per-product splits (ashPrices.csv, pepperPrices.csv, ashTrades.csv,
        pepperTrades.csv) and per-product analysis files (ashAnalysis.csv,
        pepperAnalysis.csv) with spread/microprice/imbalance computed from
        the best bid/ask level only, and tradeCount/totalQty/avgTradePrice/
        maxTradePrice/minTradePrice aggregated from trades printing at the
        same (day, timestamp). These formulas were reverse-engineered from
        the original cleaned/*Analysis.csv and spot-checked row for row
        before the day fix was applied (see tests/test_prepare_data.py).

Run with no arguments: `python prepare_data.py`. It is idempotent -- it
always reads from cleaned/raw/ and overwrites cleaned/*.csv, so running it
twice in a row produces identical output.
"""
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(ROOT, "cleaned", "raw")
OUT_DIR = os.path.join(ROOT, "cleaned")

DAY_OFFSET = 1_000_000  # > max intraday timestamp (999900); keeps globalTs monotone across days
DAY_MAP = {0: 2, 1: 1, 2: 0}

PRODUCTS = [
    ("ASH_COATED_OSMIUM", "ash"),
    ("INTARIAN_PEPPER_ROOT", "pepper"),
]


def fix_day(df):
    df = df.copy()
    df["day"] = df["day"].map(DAY_MAP)
    return df


def add_price_stats(prices):
    """Best-level spread/microprice/imbalance; NaN when either side is empty."""
    df = prices.copy()
    twoSided = df["bid_price_1"].notna() & df["ask_price_1"].notna()

    df["globalTs"] = df["day"] * DAY_OFFSET + df["timestamp"]
    df["spread"] = np.nan
    df["microprice"] = np.nan
    df["imbalance"] = np.nan

    bid = df.loc[twoSided, "bid_price_1"]
    ask = df.loc[twoSided, "ask_price_1"]
    bidVol = df.loc[twoSided, "bid_volume_1"]
    askVol = df.loc[twoSided, "ask_volume_1"]
    total = bidVol + askVol

    df.loc[twoSided, "spread"] = ask - bid
    df.loc[twoSided, "microprice"] = (bid * askVol + ask * bidVol) / total
    df.loc[twoSided, "imbalance"] = (bidVol - askVol) / total
    return df


def trade_aggregates(trades, product):
    productTrades = trades[trades["symbol"] == product]
    grouped = productTrades.groupby(["day", "timestamp"])["price"]
    agg = grouped.agg(tradeCount="count", avgTradePrice="mean",
                       maxTradePrice="max", minTradePrice="min")
    agg["totalQty"] = productTrades.groupby(["day", "timestamp"])["quantity"].sum()
    return agg.reset_index()


def build_product(prices, trades, product):
    productPrices = prices[prices["product"] == product].reset_index(drop=True)
    productPrices = add_price_stats(productPrices)
    productPrices = productPrices.sort_values(["day", "timestamp"]).reset_index(drop=True)

    productTrades = trades[trades["symbol"] == product].reset_index(drop=True)
    productTrades = productTrades.copy()
    productTrades["globalTs"] = productTrades["day"] * DAY_OFFSET + productTrades["timestamp"]
    productTrades = productTrades.sort_values(["day", "timestamp"]).reset_index(drop=True)

    agg = trade_aggregates(trades, product)
    analysis = productPrices.merge(agg, on=["day", "timestamp"], how="left")
    analysis["tradeCount"] = analysis["tradeCount"].fillna(0.0)
    analysis["totalQty"] = analysis["totalQty"].fillna(0.0)

    return productPrices, productTrades, analysis


def main():
    pricesRaw = pd.read_csv(os.path.join(RAW_DIR, "allPrices.csv"))
    tradesRaw = pd.read_csv(os.path.join(RAW_DIR, "allTrades.csv"))

    prices = fix_day(pricesRaw).sort_values(["day", "timestamp", "product"]).reset_index(drop=True)
    trades = fix_day(tradesRaw).sort_values(["day", "timestamp", "symbol"]).reset_index(drop=True)

    prices.to_csv(os.path.join(OUT_DIR, "allPrices.csv"), index=False)
    trades.to_csv(os.path.join(OUT_DIR, "allTrades.csv"), index=False)

    for product, prefix in PRODUCTS:
        productPrices, productTrades, analysis = build_product(prices, trades, product)
        productPrices.to_csv(os.path.join(OUT_DIR, f"{prefix}Prices.csv"), index=False)
        productTrades.to_csv(os.path.join(OUT_DIR, f"{prefix}Trades.csv"), index=False)
        analysis.to_csv(os.path.join(OUT_DIR, f"{prefix}Analysis.csv"), index=False)

    print("Wrote cleaned/allPrices.csv, allTrades.csv and per-product splits/analysis.")


if __name__ == "__main__":
    main()
