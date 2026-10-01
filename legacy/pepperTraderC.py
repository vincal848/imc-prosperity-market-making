"""SUPERSEDED. Kept for reference only -- this file is not part of the package and is known to be incorrect.

1. Fair value is hardcoded to pepperFairValue=12474 and never updated from
   the live book, even though PepperState.observe() tracks a live
   microprice-based fair value every tick -- `fairValue = pepperFairValue`
   ignores `pepperState.fairValue()` entirely. Pinned by
   tests/test_legacy.py::test_pepper_trader_c_ignores_its_own_tracked_fair_value.
2. Places both a buy and a sell order on every tick regardless of whether
   that side of the book is present -- the roomToBuy/roomToSell checks are
   not gated on bidPresent/askPresent, unlike every other trader in this
   repo. Pinned by
   tests/test_legacy.py::test_pepper_trader_c_quotes_both_sides_even_when_a_book_side_is_empty.

Replaced by trader.py (PepperStrategy).
"""
from datamodel import TradingState, Order
from dataclasses import dataclass, field
from collections import deque
import json


positionLimit = 80
pepperQuoteSize = 10
pepperFairValue = 12474
pepperBaseHalfSpread = 1

rollingWindow = 100
maxInventoryLean = 2


@dataclass
class PepperState:
    mids: deque = field(default_factory=lambda: deque(maxlen=rollingWindow))
    lastFairValue: float = pepperFairValue

    def observe(self, mid, microprice, bidPresent, askPresent):
        if mid > 0:
            self.mids.append(mid)

        if bidPresent and askPresent and microprice > 0:
            self.lastFairValue = microprice
        elif mid > 0:
            self.lastFairValue = mid

    def fairValue(self):
        return self.lastFairValue if self.lastFairValue > 0 else pepperFairValue

    def toDict(self):
        return {
            "mids": list(self.mids),
            "lastFairValue": self.lastFairValue,
        }

    @classmethod
    def fromDict(cls, data):
        state = cls()
        state.mids = deque(data.get("mids", []), maxlen=rollingWindow)
        state.lastFairValue = float(data.get("lastFairValue", pepperFairValue))
        return state


def inventoryLean(position):
    if position > 40:
        return 2
    if position > 15:
        return 1
    if position < -40:
        return -2
    if position < -15:
        return -1
    return 0


class Trader:
    def run(self, state: TradingState):
        try:
            stateBlob = json.loads(state.traderData) if state.traderData else {}
        except Exception:
            stateBlob = {}

        result = {}

        for product, depth in state.order_depths.items():
            if product != "INTARIAN_PEPPER_ROOT":
                continue

            pepperState = PepperState.fromDict(stateBlob[product]) if product in stateBlob else PepperState()

            buys = depth.buy_orders or {}
            sells = depth.sell_orders or {}

            bidPresent = bool(buys)
            askPresent = bool(sells)

            if bidPresent and askPresent:
                bestBid = max(buys.keys())
                bestAsk = min(sells.keys())

                bidVolume = buys[bestBid]
                askVolume = abs(sells[bestAsk])

                mid = (bestBid + bestAsk) / 2.0
                totalVolume = bidVolume + askVolume
                microprice = (bestBid * askVolume + bestAsk * bidVolume) / totalVolume if totalVolume > 0 else mid
            else:
                bestBid = max(buys.keys()) if bidPresent else 0.0
                bestAsk = min(sells.keys()) if askPresent else 0.0

                if bidPresent:
                    mid = bestBid
                elif askPresent:
                    mid = bestAsk
                else:
                    mid = pepperState.lastFairValue or pepperFairValue

                microprice = mid

            pepperState.observe(mid, microprice, bidPresent, askPresent)

            fairValue = pepperFairValue
            lean = inventoryLean(state.position.get(product, 0))
            reservationPrice = fairValue - lean

            bidPrice = int(round(reservationPrice - pepperBaseHalfSpread))
            askPrice = int(round(reservationPrice + pepperBaseHalfSpread))

            position = state.position.get(product, 0)
            roomToBuy = max(0, positionLimit - position)
            roomToSell = max(0, positionLimit + position)

            orders = []

            if roomToBuy > 0:
                buySize = min(pepperQuoteSize, roomToBuy)
                orders.append(Order(product, bidPrice, buySize))

            if roomToSell > 0:
                sellSize = min(pepperQuoteSize, roomToSell)
                orders.append(Order(product, askPrice, -sellSize))

            result[product] = orders
            stateBlob[product] = pepperState.toDict()

        traderData = json.dumps(stateBlob)
        return result, 0, traderData