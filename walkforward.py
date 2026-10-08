"""Walk-forward evaluation per docs/PROTOCOL.md and PROTOCOL-2.md: tune on day 0 only, score days 1-2 once.

Usage: python walkforward.py tune   -> every variant on day 0; writes docs/tuned.json (prints variant counts)
       python walkforward.py test   -> the day-0 picks and baselines on days 0-2, per-day PnL, both fill models
"""
import itertools
import json
import os
import sys

import numpy as np

import backtest
import baselines
import trader

PEPPER, ASH = "INTARIAN_PEPPER_ROOT", "ASH_COATED_OSMIUM"
TUNED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "tuned.json")
STRESS = dict(passiveFillFraction=0.5, strictTradeThrough=True)
PROTOCOL_1_VARIANTS = 19  # see PROTOCOL.md; the 500-tick-window search

# Protocol 2, part 1: (trendThreshold, overlay). 2.0 twice: "cal" collapses to its 2.0 floor.
THRESHOLDS = {"fixed2": 2.0, "cal": 2.0, "rw99": 3.7}
PEPPER_VARIANTS = list(itertools.product(THRESHOLDS, (0, 10)))
# Protocol 2, part 2: coordinate descent over Ash settings, in this order, starting from the learned MM.
ASH_START = dict(width=0, skewScale=1.0, anchor=0.0, takeEdge=0, size=10)
ASH_DIMS = {"width": (1, 2, 3, 4, 6), "skewScale": (0.0, 0.5), "anchor": (0.5, 1.0),
            "takeEdge": (2, 4, 6), "size": (20,)}


def rw_false_rate(threshold: float, paths: int = 1000, ticks: int = 30000, seed: int = 0) -> float:
    """Share of seeded i.i.d. random-walk paths whose |expanding t| ever exceeds threshold (500-tick warm-up)."""
    rng, n = np.random.default_rng(seed), np.arange(1, ticks + 1)
    peaks = [np.abs(np.cumsum(rng.normal(0, 1, ticks)) / np.sqrt(n))[500:].max() for _ in range(paths)]
    return float(np.mean(np.array(peaks) > threshold))


def configure(threshold: float, band: int, ash: dict) -> None:
    trader.trendThreshold, trader.overlay = threshold, band
    for key, value in ash.items():
        setattr(trader.strategies[ASH], key, value)


def run(product: str, days: list[int], **fill) -> list[float]:
    return list(backtest.day_pnl(backtest.run_backtest(trader.Trader(), product, days, **fill)))


def baseline(product: str, days: list[int], **fill) -> list[float]:
    base = (baselines.BuyAndHoldTrader() if product == PEPPER
            else baselines.FixedValueMarketMaker(fairValue=10000, halfSpread=2, quoteSize=10))
    return list(backtest.day_pnl(backtest.run_backtest(base, product, days, **fill)))


def tune() -> None:
    scores = {}
    for name, band in PEPPER_VARIANTS:
        configure(THRESHOLDS[name], band, ASH_START)
        scores[(name, band)] = run(PEPPER, [0])[0] + run(ASH, [0])[0]
        print(name, band, round(scores[(name, band)]), "false-engagement", rw_false_rate(THRESHOLDS[name], paths=200))
    eligible = [v for v in PEPPER_VARIANTS if rw_false_rate(THRESHOLDS[v[0]], paths=200) <= 0.05]
    pepper = max(eligible, key=scores.get)

    ash, best = dict(ASH_START), None
    configure(THRESHOLDS[pepper[0]], pepper[1], ash)
    best = run(ASH, [0], **STRESS)[0]
    ashVariants = 1
    print("ash start (stressed day 0)", best, " fixed-value baseline (stressed day 0)", baseline(ASH, [0], **STRESS)[0])
    for dim, values in ASH_DIMS.items():
        chosen = ash[dim]
        for value in values:
            configure(THRESHOLDS[pepper[0]], pepper[1], {**ash, dim: value})
            score = run(ASH, [0], **STRESS)[0]
            ashVariants += 1
            print(dim, value, score)
            if score > best:
                best, chosen = score, value
        ash[dim] = chosen
    counts = {"protocol1": PROTOCOL_1_VARIANTS, "pepper": len(PEPPER_VARIANTS), "ash": ashVariants}
    counts["total"] = sum(counts.values())
    with open(TUNED, "w") as handle:
        json.dump({"pepper": [THRESHOLDS[pepper[0]], pepper[1], pepper[0]], "ash": ash, "variants": counts}, handle)
    print("pepper pick", pepper, "ash pick", ash, "variants", counts)


def test() -> None:
    with open(TUNED) as handle:
        tuned = json.load(handle)
    for label, fill in (("unstressed", {}), ("stressed", STRESS)):
        for product in (PEPPER, ASH):
            configure(tuned["pepper"][0], tuned["pepper"][1], tuned["ash"])
            print(label, product, "tuned", run(product, [0, 1, 2], **fill), "baseline", baseline(product, [0, 1, 2], **fill))
            if product == ASH:
                configure(tuned["pepper"][0], tuned["pepper"][1], ASH_START)
                print(label, product, "learned MM (start)", run(product, [0, 1, 2], **fill))


if __name__ == "__main__":
    tune() if sys.argv[1] == "tune" else test()
