"""Unit tests for backtest.py's fill model and position-limit enforcement."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pandas as pd

import backtest
from datamodel import Order

PRODUCT = "ASH_COATED_OSMIUM"

PRICE_COLUMNS = [
    "day", "timestamp", "globalTs",
    "bid_price_1", "bid_volume_1", "bid_price_2", "bid_volume_2", "bid_price_3", "bid_volume_3",
    "ask_price_1", "ask_volume_1", "ask_price_2", "ask_volume_2", "ask_price_3", "ask_volume_3",
    "mid_price",
]

TRADE_COLUMNS = ["day", "timestamp", "symbol", "price", "quantity", "globalTs"]


def one_tick_prices(bids=(), asks=(), mid=100.0, day=0, timestamp=0):
    row = {column: float("nan") for column in PRICE_COLUMNS}
    row.update({"day": day, "timestamp": timestamp, "globalTs": timestamp, "mid_price": mid})
    for level, (price, volume) in enumerate(bids, start=1):
        row[f"bid_price_{level}"] = price
        row[f"bid_volume_{level}"] = volume
    for level, (price, volume) in enumerate(asks, start=1):
        row[f"ask_price_{level}"] = price
        row[f"ask_volume_{level}"] = volume
    return pd.DataFrame([row])


def trades_df(prints, day=0, timestamp=0):
    rows = [{"day": day, "timestamp": timestamp, "symbol": PRODUCT, "price": price,
              "quantity": quantity, "globalTs": timestamp} for price, quantity in prints]
    return pd.DataFrame(rows, columns=TRADE_COLUMNS)


class FixedOrdersTrader:
    """Always returns the same orders, regardless of state."""

    def __init__(self, orders):
        self.orders = orders

    def run(self, state):
        return {PRODUCT: list(self.orders)}, 0, state.traderData


def run_one_tick(orders, bids=(), asks=(), prints=()):
    prices = one_tick_prices(bids=bids, asks=asks)
    trades = trades_df(prints)
    backtester = backtest.Backtester(FixedOrdersTrader(orders), PRODUCT, prices=prices, trades=trades)
    records = backtester.run()
    return backtester, records


def test_a_crossing_buy_order_walks_price_levels_by_visible_volume():
    # Buying 12 @ 102 should take all 5 @ 101 then 7 of the 10 @ 102.
    orders = [Order(PRODUCT, 102, 12)]
    backtester, _records = run_one_tick(orders, asks=[(101, 5), (102, 10)])

    assert backtester.position == 12
    assert backtester.cash == -(5 * 101 + 7 * 102)


def test_a_crossing_sell_order_walks_price_levels_by_visible_volume():
    orders = [Order(PRODUCT, 98, -12)]
    backtester, _records = run_one_tick(orders, bids=[(99, 5), (98, 10)])

    assert backtester.position == -12
    assert backtester.cash == 5 * 99 + 7 * 98


def test_a_resting_sell_fills_against_a_market_trade_that_prints_through_it():
    # Our ask at 105 does not cross the (low) bid book, but a trade prints at 106.
    orders = [Order(PRODUCT, 105, -3)]
    backtester, _records = run_one_tick(orders, bids=[(90, 5)], prints=[(106, 2)])

    assert backtester.position == -2
    assert backtester.cash == 2 * 105


def test_a_resting_buy_does_not_fill_against_a_trade_that_does_not_reach_it():
    orders = [Order(PRODUCT, 95, 3)]
    backtester, _records = run_one_tick(orders, asks=[(110, 5)], prints=[(96, 2)])

    assert backtester.position == 0
    assert backtester.cash == 0


def test_position_limit_breach_rejects_every_order_for_the_product_that_tick():
    # Buying 90 alone would breach the 80 limit; the accompanying sell order
    # is otherwise harmless, but IMC rejects the whole batch on a breach.
    orders = [Order(PRODUCT, 200, 90), Order(PRODUCT, 1, -5)]
    backtester, _records = run_one_tick(orders, bids=[(1, 100)], asks=[(200, 100)])

    assert backtester.position == 0
    assert backtester.cash == 0


def test_mark_to_market_pnl_ignores_the_zero_sentinel_for_an_empty_book():
    # IMC writes mid_price=0 (not NaN) when there is no book at all; the mark
    # should carry the last known mid forward instead of marking to zero.
    firstTick = one_tick_prices(bids=[(100, 5)], asks=[(102, 5)], mid=101.0, timestamp=0)
    emptyTick = one_tick_prices(mid=0.0, timestamp=100)
    prices = pd.concat([firstTick, emptyTick], ignore_index=True)
    trades = trades_df([])

    backtester = backtest.Backtester(FixedOrdersTrader([]), PRODUCT, prices=prices, trades=trades)
    records = backtester.run()

    assert records["mid"].iloc[-1] == 101.0


def test_day_pnl_sums_to_the_final_cumulative_pnl():
    records = pd.DataFrame({
        "day": [0, 0, 1, 1, 2, 2],
        "pnl": [10.0, 15.0, 15.0, 20.0, 20.0, 50.0],
    })
    perDay = backtest.day_pnl(records)
    assert perDay.sum() == records["pnl"].iloc[-1]
