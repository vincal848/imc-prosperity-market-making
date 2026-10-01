"""Minimal datamodel mirroring IMC Prosperity's public interface.

IMC provides this module at competition time; it is not published as a
package, so it has to be vendored by every team that wants to run or backtest
a Trader locally. This is a stdlib-only reimplementation of the subset
TraderC1 (now trader.py) actually uses: Listing, Order, OrderDepth, Trade,
ConversionObservation, Observation and TradingState, with the same field
names and shapes as the real thing, so a submission compiled against this
file is interface-compatible with IMC's engine. It does not include the IMC
matching engine itself -- see backtest.py for a local replay.
"""
from json import JSONEncoder


Time = int
Symbol = str
Product = str
Position = int
UserId = str


class Listing:
    def __init__(self, symbol, product, denomination):
        self.symbol = symbol
        self.product = product
        self.denomination = denomination


class ConversionObservation:
    def __init__(self, bidPrice, askPrice, transportFees, exportTariff, importTariff, sunlightIndex=0.0, humidity=0.0):
        self.bidPrice = bidPrice
        self.askPrice = askPrice
        self.transportFees = transportFees
        self.exportTariff = exportTariff
        self.importTariff = importTariff
        self.sunlightIndex = sunlightIndex
        self.humidity = humidity


class Observation:
    def __init__(self, plainValueObservations, conversionObservations):
        self.plainValueObservations = plainValueObservations
        self.conversionObservations = conversionObservations


class Order:
    def __init__(self, symbol, price, quantity):
        self.symbol = symbol
        self.price = price
        self.quantity = quantity

    def __str__(self):
        return f"({self.symbol}, {self.price}, {self.quantity})"

    __repr__ = __str__


class OrderDepth:
    def __init__(self):
        self.buy_orders = {}
        self.sell_orders = {}


class Trade:
    def __init__(self, symbol, price, quantity, buyer=None, seller=None, timestamp=0):
        self.symbol = symbol
        self.price = price
        self.quantity = quantity
        self.buyer = buyer
        self.seller = seller
        self.timestamp = timestamp

    def __str__(self):
        return f"({self.symbol}, {self.buyer} << {self.seller}, {self.price}, {self.quantity}, {self.timestamp})"

    __repr__ = __str__


class TradingState:
    def __init__(self, traderData, timestamp, listings, order_depths,
                 own_trades, market_trades, position, observations):
        self.traderData = traderData
        self.timestamp = timestamp
        self.listings = listings
        self.order_depths = order_depths
        self.own_trades = own_trades
        self.market_trades = market_trades
        self.position = position
        self.observations = observations


class ProsperityEncoder(JSONEncoder):
    def default(self, o):
        return o.__dict__
