"""Trivial comparison traders, used only by run.py's `compare` command.

Neither of these is meant to be submitted -- they exist to answer "is the
rebuilt market maker actually earning its complexity", per product:

  - FixedValueMarketMaker: quotes a fixed symmetric spread around a constant
    fair value, ignoring all market data beyond whether a book side exists.
    A sensible baseline for ASH_COATED_OSMIUM, which mean-reverts.
  - BuyAndHoldTrader: crosses the book once, buying whatever is available at
    the best ask (up to the position limit), then holds forever. A sensible
    baseline for INTARIAN_PEPPER_ROOT, which trends.
"""
from datamodel import Order

POSITION_LIMIT = 80


class FixedValueMarketMaker:
    """Quotes fairValue +/- halfSpread, size quoteSize, whenever that side of the book exists."""

    def __init__(self, fairValue, halfSpread=2, quoteSize=10):
        self.fairValue = fairValue
        self.halfSpread = halfSpread
        self.quoteSize = quoteSize

    def run(self, state):
        result = {}
        for product, depth in state.order_depths.items():
            bidPresent = bool(depth.buy_orders)
            askPresent = bool(depth.sell_orders)
            position = state.position.get(product, 0)

            roomToBuy = max(0, POSITION_LIMIT - position)
            roomToSell = max(0, POSITION_LIMIT + position)

            orders = []
            if bidPresent and roomToBuy > 0:
                orders.append(Order(product, int(self.fairValue - self.halfSpread), min(self.quoteSize, roomToBuy)))
            if askPresent and roomToSell > 0:
                orders.append(Order(product, int(self.fairValue + self.halfSpread), -min(self.quoteSize, roomToSell)))

            result[product] = orders

        return result, 0, state.traderData


class BuyAndHoldTrader:
    """Buys up to the position limit on the first tick it sees a book, then holds."""

    def __init__(self):
        self.bought = False

    def run(self, state):
        result = {}
        for product, depth in state.order_depths.items():
            position = state.position.get(product, 0)
            orders = []

            if not self.bought and depth.sell_orders and position < POSITION_LIMIT:
                bestAsk = min(depth.sell_orders)
                size = min(POSITION_LIMIT - position, abs(depth.sell_orders[bestAsk]))
                if size > 0:
                    orders.append(Order(product, bestAsk, size))
                    self.bought = True

            result[product] = orders

        return result, 0, state.traderData
