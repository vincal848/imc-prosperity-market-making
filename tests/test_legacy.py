"""Regression tests pinning the defects documented atop each legacy/ file."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from datamodel import Observation, OrderDepth, TradingState
from legacy import pepperTraderC, pepperWTradeSignalASH, pepperWTradeSignalASH1

PEPPER = "INTARIAN_PEPPER_ROOT"
ASH = "ASH_COATED_OSMIUM"


def make_state(order_depths, position=None, timestamp=0):
    return TradingState(
        traderData="",
        timestamp=timestamp,
        listings={},
        order_depths=order_depths,
        own_trades={},
        market_trades={},
        position=position or {},
        observations=Observation({}, {}),
    )


def depth(buys, sells):
    """buys/sells are {price: positive volume}; sell_orders are stored negative per convention."""
    d = OrderDepth()
    d.buy_orders = dict(buys)
    d.sell_orders = {price: -volume for price, volume in sells.items()}
    return d


def test_pepper_trader_c_ignores_its_own_tracked_fair_value():
    # Book sits around 13000, far from the hardcoded pepperFairValue=12474.
    state = make_state({PEPPER: depth({12999: 10}, {13001: 10})})
    orders, _conversions, _traderData = pepperTraderC.Trader().run(state)

    prices = [order.price for order in orders[PEPPER]]
    # If the trader actually used its tracked fair value it would quote near
    # 13000; instead every quote sits within a tick or two of the hardcoded
    # 12474 constant, regardless of where the market actually is.
    assert all(abs(price - pepperTraderC.pepperFairValue) <= 2 for price in prices)
    assert all(abs(price - 13000) > 500 for price in prices)


def test_pepper_trader_c_quotes_both_sides_even_when_a_book_side_is_empty():
    state = make_state({PEPPER: depth({}, {12480: 10})})  # no bid side at all
    orders, _conversions, _traderData = pepperTraderC.Trader().run(state)

    sides = {1 if order.quantity > 0 else -1 for order in orders[PEPPER]}
    assert sides == {1, -1}  # both a buy and a sell, despite the missing bid side


def test_pepper_w_trade_signal_ash_never_reads_the_ash_state():
    pepperBook = depth({12480: 10}, {12482: 10})
    lowAsh = depth({9000: 10}, {9002: 10})
    highAsh = depth({11000: 10}, {11002: 10})

    stateLowAsh = make_state({PEPPER: pepperBook, ASH: lowAsh})
    stateHighAsh = make_state({PEPPER: pepperBook, ASH: highAsh})

    ordersLow, _c1, _d1 = pepperWTradeSignalASH.Trader().run(stateLowAsh)
    ordersHigh, _c2, _d2 = pepperWTradeSignalASH.Trader().run(stateHighAsh)

    pricesLow = sorted(order.price for order in ordersLow[PEPPER])
    pricesHigh = sorted(order.price for order in ordersHigh[PEPPER])
    assert pricesLow == pricesHigh  # swapping the Ash book changes nothing about the Pepper quote


def test_pepper_w_trade_signal_ash1_is_unaffected_by_an_ash_book_too():
    pepperBook = depth({12480: 10}, {12482: 10})
    stateWithAsh = make_state({PEPPER: pepperBook, ASH: depth({9000: 10}, {9002: 10})})
    stateWithoutAsh = make_state({PEPPER: pepperBook})

    ordersWith, _c1, _d1 = pepperWTradeSignalASH1.Trader().run(stateWithAsh)
    ordersWithout, _c2, _d2 = pepperWTradeSignalASH1.Trader().run(stateWithoutAsh)

    pricesWith = sorted(order.price for order in ordersWith[PEPPER])
    pricesWithout = sorted(order.price for order in ordersWithout[PEPPER])
    assert pricesWith == pricesWithout
