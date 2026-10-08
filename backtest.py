"""Deterministic local replay of a Trader against cleaned/ order books.

There is no public IMC matching engine, so this is a documented, simplified
model of one:

  - Crossing fills: an order that crosses the visible book (bid price >=
    some ask level, or ask price <= some bid level) fills immediately
    against that tick's book, walking up to 3 price levels in price-priority
    order, capped by each level's visible volume.
  - Passive fills: whatever quantity doesn't cross the book rests, and fills
    against this tick's market_trades that print through our price (a trade
    at or below our bid, or at or above our ask), capped by the printed
    trade quantity, filled at OUR price (we assume full price improvement
    for the resting side, which is the standard backtest convention when the
    real counterparty-matching logic is unknown).
  - No look-ahead: the trader's state.market_trades is the PREVIOUS tick's
    prints; resting quotes fill against the CURRENT tick's prints, which the
    trader has not seen when it quotes.
  - Optional stress knobs: passiveFillFraction scales the printed quantity a
    resting order may take; strictTradeThrough requires the print to be
    strictly through our price (a print AT our price does not fill us).
  - Position limit (80): if fully filling every order for a product this
    tick could push the position beyond +-80 in either direction, every
    order for that product is rejected for the tick -- this mirrors IMC's
    own rule (breach -> reject the whole batch, not a partial clip).

PnL is mark-to-market: cash from fills, plus open position valued at the
tick's mid price (carried forward on ticks where the book is one-sided or
empty).
"""
import argparse
import os

import pandas as pd

from datamodel import Observation, Order, OrderDepth, Trade, TradingState

ROOT = os.path.dirname(os.path.abspath(__file__))
CLEANED_DIR = os.path.join(ROOT, "cleaned")

POSITION_LIMIT = 80

PRODUCT_PREFIX = {
    "ASH_COATED_OSMIUM": "ash",
    "INTARIAN_PEPPER_ROOT": "pepper",
}


def load_product(product, days=None):
    prefix = PRODUCT_PREFIX[product]
    prices = pd.read_csv(os.path.join(CLEANED_DIR, f"{prefix}Prices.csv"))
    trades = pd.read_csv(os.path.join(CLEANED_DIR, f"{prefix}Trades.csv"))
    if days is not None:
        prices = prices[prices["day"].isin(days)]
        trades = trades[trades["day"].isin(days)]
    prices = prices.sort_values(["day", "timestamp"]).reset_index(drop=True)
    trades = trades.sort_values(["day", "timestamp"]).reset_index(drop=True)
    return prices, trades


def build_order_depth(row):
    depth = OrderDepth()
    for level in (1, 2, 3):
        bidPrice = getattr(row, f"bid_price_{level}")
        bidVolume = getattr(row, f"bid_volume_{level}")
        if pd.notna(bidPrice) and pd.notna(bidVolume):
            depth.buy_orders[int(bidPrice)] = int(bidVolume)

        askPrice = getattr(row, f"ask_price_{level}")
        askVolume = getattr(row, f"ask_volume_{level}")
        if pd.notna(askPrice) and pd.notna(askVolume):
            depth.sell_orders[int(askPrice)] = -int(askVolume)
    return depth


def group_trades(trades):
    grouped = {}
    for row in trades.itertuples():
        grouped.setdefault((row.day, row.timestamp), []).append(
            Trade(row.symbol, int(row.price), int(row.quantity), timestamp=row.globalTs)
        )
    return grouped


class Backtester:
    """Replays one Trader against one product's prices/trades."""

    def __init__(self, trader, product: str, days=None, prices=None, trades=None,
                 passiveFillFraction: float = 1.0, strictTradeThrough: bool = False):
        self.trader = trader
        self.passiveFillFraction = passiveFillFraction
        self.strictTradeThrough = strictTradeThrough
        self.product = product
        if prices is None or trades is None:
            prices, trades = load_product(product, days)
        self.prices = prices
        self.trades = trades
        self.tradesByTick = group_trades(self.trades)

        self.position = 0
        self.cash = 0.0
        self.traderData = ""
        self.lastMid = None
        self.records = []
        self.prevTrades = []

    def run(self):
        for row in self.prices.itertuples():
            depth = build_order_depth(row)
            marketTrades = self.tradesByTick.get((row.day, row.timestamp), [])

            # IMC writes mid_price=0 (not NaN) on ticks with no book at all; treat
            # that the same as missing and carry the last known mid forward.
            mid = row.mid_price if pd.notna(row.mid_price) and row.mid_price > 0 else self.lastMid
            if mid is not None:
                self.lastMid = mid

            state = TradingState(
                traderData=self.traderData,
                timestamp=row.globalTs,
                listings={},
                order_depths={self.product: depth},
                own_trades={},
                market_trades={self.product: self.prevTrades},
                position={self.product: self.position},
                observations=Observation({}, {}),
            )

            orders, _conversions, self.traderData = self.trader.run(state)
            productOrders = orders.get(self.product, [])
            self._apply(productOrders, depth, marketTrades)
            self.prevTrades = marketTrades

            markToMarket = self.cash + self.position * (mid if mid is not None else 0.0)
            self.records.append({
                "day": row.day,
                "timestamp": row.timestamp,
                "globalTs": row.globalTs,
                "mid": mid,
                "position": self.position,
                "cash": self.cash,
                "pnl": markToMarket,
            })

        return pd.DataFrame(self.records)

    def _apply(self, orders, depth, marketTrades):
        if not orders:
            return

        totalBuy = sum(o.quantity for o in orders if o.quantity > 0)
        totalSell = sum(-o.quantity for o in orders if o.quantity < 0)
        if self.position + totalBuy > POSITION_LIMIT or self.position - totalSell < -POSITION_LIMIT:
            return  # IMC rejects the whole batch for this product on a breach, not a partial clip

        for order in orders:
            if order.quantity > 0:
                self._fill_buy(order, depth, marketTrades)
            elif order.quantity < 0:
                self._fill_sell(order, depth, marketTrades)

    def _fill_buy(self, order, depth, marketTrades):
        remaining = order.quantity

        for askPrice in sorted(depth.sell_orders):
            if remaining <= 0 or askPrice > order.price:
                break
            available = abs(depth.sell_orders[askPrice])
            quantity = min(remaining, available)
            self._settle(quantity, askPrice)
            remaining -= quantity

        for trade in marketTrades:
            if remaining <= 0:
                break
            if self._through(trade.price, order.price, buy=True):
                quantity = min(remaining, int(trade.quantity * self.passiveFillFraction))
                self._settle(quantity, order.price)
                remaining -= quantity

    def _fill_sell(self, order, depth, marketTrades):
        remaining = -order.quantity

        for bidPrice in sorted(depth.buy_orders, reverse=True):
            if remaining <= 0 or bidPrice < order.price:
                break
            available = depth.buy_orders[bidPrice]
            quantity = min(remaining, available)
            self._settle(-quantity, bidPrice)
            remaining -= quantity

        for trade in marketTrades:
            if remaining <= 0:
                break
            if self._through(trade.price, order.price, buy=False):
                quantity = min(remaining, int(trade.quantity * self.passiveFillFraction))
                self._settle(-quantity, order.price)
                remaining -= quantity

    def _through(self, tradePrice: float, orderPrice: float, buy: bool) -> bool:
        if self.strictTradeThrough:
            return tradePrice < orderPrice if buy else tradePrice > orderPrice
        return tradePrice <= orderPrice if buy else tradePrice >= orderPrice

    def _settle(self, signedQuantity, price):
        self.position += signedQuantity
        self.cash -= signedQuantity * price


def run_backtest(trader, product: str, days=None, **fillKwargs) -> pd.DataFrame:
    return Backtester(trader, product, days, **fillKwargs).run()


def day_pnl(records: pd.DataFrame) -> pd.Series:
    """Realized mark-to-market PnL per day: last tick's cumulative pnl minus the previous day's."""
    perDayEnd = records.groupby("day")["pnl"].last().sort_index()
    return perDayEnd.diff().fillna(perDayEnd.iloc[0] if len(perDayEnd) else 0.0)


def _parse_args():
    parser = argparse.ArgumentParser(description="Backtest a Trader against cleaned/ order books.")
    parser.add_argument("--product", choices=["ASH_COATED_OSMIUM", "INTARIAN_PEPPER_ROOT"], required=True)
    parser.add_argument("--days", type=int, nargs="*", default=None)
    return parser.parse_args()


if __name__ == "__main__":
    import trader as traderModule

    args = _parse_args()
    records = run_backtest(traderModule.Trader(), args.product, args.days)
    print(records.tail())
    print("Per-day PnL:")
    print(day_pnl(records))
