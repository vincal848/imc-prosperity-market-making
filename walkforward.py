"""Walk-forward evaluation per docs/PROTOCOL.md: tune on day 0 only, score days 1-2 once.

Usage: python walkforward.py tune   -> every variant on day 0 (prints the variant count)
       python walkforward.py test   -> the day-0 winner (+ baselines) on days 0-2, per-day PnL
"""
import itertools
import sys

import backtest
import baselines
import trader

PEPPER, ASH = "INTARIAN_PEPPER_ROOT", "ASH_COATED_OSMIUM"
INF = float("inf")
# (trendLookback, trendThreshold, overlay); threshold inf = the original market maker.
VARIANTS = [(1000, INF, 10)] + list(itertools.product((500, 1000, 2000), (0.5, 1.0, 1.5), (0, 10)))


def configure(lookback: int, threshold: float, band: int) -> None:
    trader.trendLookback, trader.trendThreshold, trader.overlay = lookback, threshold, band


def run(product: str, days: list[int], **fill) -> list[float]:
    return list(backtest.day_pnl(backtest.run_backtest(trader.Trader(), product, days, **fill)))


def baseline(product: str, days: list[int], **fill) -> list[float]:
    base = (baselines.BuyAndHoldTrader() if product == PEPPER
            else baselines.FixedValueMarketMaker(fairValue=10000, halfSpread=2, quoteSize=10))
    return list(backtest.day_pnl(backtest.run_backtest(base, product, days, **fill)))


def tune() -> tuple:
    scores = {}
    for variant in VARIANTS:
        configure(*variant)
        scores[variant] = run(PEPPER, [0])[0] + run(ASH, [0])[0]  # one config, both products
        print(variant, round(scores[variant]))
    best = max(scores, key=scores.get)
    print(f"variants tried: {len(VARIANTS)}  day-0 winner: {best}")
    return best


def test(variant: tuple) -> None:
    configure(*variant)
    for product in (PEPPER, ASH):
        print(product, "strategy", run(product, [0, 1, 2]), "baseline", baseline(product, [0, 1, 2]))


if __name__ == "__main__":
    if sys.argv[1] == "tune":
        tune()
    else:
        test((int(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4])))
