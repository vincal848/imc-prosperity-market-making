"""Walk-forward evaluation per docs/PROTOCOL.md and PROTOCOL-2.md: tune on day 0 only, score days 1-2 once.

Usage: python walkforward.py tune3     -> protocol 3: the 4 guard variants on day 0 (stressed), added to docs/tuned.json
       python walkforward.py calibrate -> protocol 3 variance-ratio thresholds from random walks (no variants scored)
       python walkforward.py tune   -> every variant on day 0; writes docs/tuned.json (prints variant counts)
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
ASH_START = dict(width=0, skewScale=1.0, anchor=0.0, takeEdge=0, size=10, guardLag=0)
ASH_DIMS = {"width": (1, 2, 3, 4, 6), "skewScale": (0.0, 0.5), "anchor": (0.5, 1.0),
            "takeEdge": (2, 4, 6), "size": (20,)}


# Protocol 3: variance-ratio guard on the Ash MM. (lag, fallback) in declared order.
GUARD_VARIANTS = [(5, "passive"), (5, "flat"), (20, "passive"), (20, "flat")]
GUARD_MAX_FALSE_RATE = 0.01


def vr_null_z(lag: int, seed: int, paths: int = 200, ticks: int = 5000, stride: int = 25) -> np.ndarray:
    """z of VR(lag) on rolling 500-mid windows of driftless Gaussian walks with Ash's day-0 vol."""
    prices, _ = backtest.load_product(ASH, [0])
    mid = prices["mid_price"][prices["mid_price"] > 0].to_numpy()
    sigma, rng = float(np.std(np.diff(mid))), np.random.default_rng(seed)
    walks = np.cumsum(rng.normal(0, sigma, (paths, ticks)), axis=1)
    return np.array([trader.varianceRatioZ(w[end - trader.rollingWindow:end], lag)
                     for w in walks for end in range(trader.rollingWindow, ticks, stride)])


def vr_threshold(lag: int) -> float:
    """c such that z < -c on at most GUARD_MAX_FALSE_RATE of null ticks; verified on an independent seed set."""
    c = -float(np.quantile(vr_null_z(lag, seed=0), GUARD_MAX_FALSE_RATE))
    check = float(np.mean(vr_null_z(lag, seed=1) < -c))
    assert check <= 2 * GUARD_MAX_FALSE_RATE, f"lag {lag}: threshold {c} engages {check} of independent null ticks"
    print("lag", lag, "threshold", round(c, 3), "false-engagement (independent seeds)", round(check, 4))
    return c


def rw_false_rate(threshold: float, paths: int = 1000, ticks: int = 30000, seed: int = 0) -> float:
    """Share of seeded i.i.d. random-walk paths whose |expanding t| ever exceeds threshold (500-tick warm-up)."""
    rng, n = np.random.default_rng(seed), np.arange(1, ticks + 1)
    peaks = [np.abs(np.cumsum(rng.normal(0, 1, ticks)) / np.sqrt(n))[500:].max() for _ in range(paths)]
    return float(np.mean(np.array(peaks) > threshold))


def tune3() -> None:
    """Protocol 3: hold the protocol-2 pick fixed, score each guard variant on stressed day 0, keep the best (ties: earlier)."""
    with open(TUNED) as handle:
        tuned = json.load(handle)
    configure(tuned["pepper"][0], tuned["pepper"][1], tuned["ash"])
    print("unguarded (stressed day 0)", run(ASH, [0], **STRESS)[0], " fixed-value baseline", baseline(ASH, [0], **STRESS)[0])
    thresholds = {lag: vr_threshold(lag) for lag in sorted({lag for lag, _ in GUARD_VARIANTS})}
    best, pick = None, None
    for lag, fallback in GUARD_VARIANTS:
        guard = dict(guardLag=lag, guardThreshold=thresholds[lag], guardFlat=fallback == "flat")
        configure(tuned["pepper"][0], tuned["pepper"][1], {**tuned["ash"], **guard})
        score = run(ASH, [0], **STRESS)[0]
        print("guard", lag, fallback, score)
        if best is None or score > best:
            best, pick = score, guard
    tuned["guard"] = pick
    tuned["variants"]["protocol3"] = len(GUARD_VARIANTS)
    tuned["variants"]["total"] = sum(v for k, v in tuned["variants"].items() if k != "total")
    with open(TUNED, "w") as handle:
        json.dump(tuned, handle)
    print("guard pick", pick, "variants", tuned["variants"])


def calibrate() -> None:
    for lag in sorted({lag for lag, _ in GUARD_VARIANTS}):
        vr_threshold(lag)


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
    guarded = {**tuned["ash"], **tuned["guard"]}
    for label, fill in (("unstressed", {}), ("stressed", STRESS)):
        for product in (PEPPER, ASH):
            configure(tuned["pepper"][0], tuned["pepper"][1], guarded)
            print(label, product, "tuned", run(product, [0, 1, 2], **fill), "baseline", baseline(product, [0, 1, 2], **fill))
            if product == ASH:
                configure(tuned["pepper"][0], tuned["pepper"][1], {**tuned["ash"], "guardLag": 0})
                print(label, product, "unguarded protocol-2 pick", run(product, [0, 1, 2], **fill))
                configure(tuned["pepper"][0], tuned["pepper"][1], ASH_START)
                print(label, product, "learned MM (start)", run(product, [0, 1, 2], **fill))


if __name__ == "__main__":
    {"calibrate": calibrate, "tune": tune, "tune3": tune3, "test": test}[sys.argv[1]]()
