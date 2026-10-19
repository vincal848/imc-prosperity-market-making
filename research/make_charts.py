"""Regenerate the charts in research/img/ used by research/WALKTHROUGH.md.

Run from the repo root after `python prepare_data.py`:
    python research/make_charts.py
"""
import os
import sys
import tempfile

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, "research")
DATA = os.path.join(HERE, "data")
IMG = os.path.join(HERE, "img")
sys.path[:0] = [ROOT, os.path.join(HERE, "round0")]

import backtest  # noqa: E402
import baselines  # noqa: E402
import trader as traderModule  # noqa: E402
from ProsperityBootstrap import bootstrap_day  # noqa: E402

BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
INK, MUTED = "#52514e", "#898781"
ASH, PEPPER = "ASH_COATED_OSMIUM", "INTARIAN_PEPPER_ROOT"
STRESS = dict(passiveFillFraction=0.5, strictTradeThrough=True)

plt.rcParams.update({
    "figure.facecolor": "#fcfcfb", "axes.facecolor": "#fcfcfb", "savefig.facecolor": "#fcfcfb",
    "axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.grid": True, "grid.color": "#e6e5e1", "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "lines.linewidth": 1.2,
    "font.size": 10, "axes.formatter.useoffset": False, "axes.titlesize": 11, "axes.titleweight": "bold", "legend.frameon": False,
})


def save(fig, name):
    for ax in fig.axes:
        for axis in (ax.xaxis, ax.yaxis):
            if isinstance(axis.get_major_formatter(), matplotlib.ticker.ScalarFormatter):
                axis.set_major_formatter(matplotlib.ticker.StrMethodFormatter("{x:,.10g}"))
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, name), dpi=120)
    plt.close(fig)
    print("wrote", name)


def read(round_, kind, day):
    return pd.read_csv(os.path.join(DATA, f"round{round_}", f"{kind}_round_{round_}_day_{day}.csv"), sep=";")


def chrono_prices(round_, files):
    """Concatenate days in true chronological order (by the file's own `day` column), two-sided rows only."""
    df = pd.concat([read(round_, "prices", d) for d in files], ignore_index=True)
    df = df[(df.bid_price_1 > 0) & (df.ask_price_1 > 0)].copy()
    return df.sort_values(["day", "timestamp"]).reset_index(drop=True)


# ---------------------------------------------------------------- round 0

def r0_overview(p):
    fig, (a, b) = plt.subplots(2, 1, figsize=(10, 6.5))
    em = p[p["product"] == "EMERALDS"].reset_index(drop=True).iloc[:400]
    a.step(em.index, em.ask_price_1, color=ORANGE, where="post", label="bot best ask")
    a.step(em.index, em.mid_price, color=INK, where="post", label="mid", linewidth=1)
    a.step(em.index, em.bid_price_1, color=BLUE, where="post", label="bot best bid")
    a.axhline(10000, color=MUTED, linestyle="--", linewidth=0.8)
    a.set_title("EMERALDS: bots usually quote 10,000 +/- 8 (first 400 ticks)")
    a.set_xlabel("tick")
    a.set_ylim(9989, 10013)
    a.legend(loc="upper center", ncol=3, bbox_to_anchor=(0.5, 1.0))

    to = p[p["product"] == "TOMATOES"].reset_index(drop=True)
    b.plot(to.index, to.mid_price, color=BLUE, linewidth=0.8)
    split = (to.day == to.day.max()).idxmax()
    b.axvline(split, color=MUTED, linestyle="--", linewidth=0.8)
    for x, label in ((split * 0.02, "day -2"), (split * 1.02, "day -1")):
        b.text(x, to.mid_price.max(), label, color=MUTED, va="top")
    b.set_title("TOMATOES: a drifting mid with no fixed anchor (both days, chronological)")
    b.set_xlabel("tick")
    b.set_ylabel("mid price")
    save(fig, "r0_overview.png")


def r0_ema_signal(p):
    to = p[(p["product"] == "TOMATOES") & (p.day == -2)].reset_index(drop=True)
    fast = to.mid_price.ewm(alpha=0.18, adjust=False).mean()
    slow = to.mid_price.ewm(alpha=0.04, adjust=False).mean()
    trend = fast - slow
    w = slice(3000, 4500)
    x = to.index[w]
    fig, (a, b) = plt.subplots(2, 1, figsize=(10, 6), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
    a.plot(x, to.mid_price[w], color=MUTED, linewidth=0.8, label="mid")
    a.plot(x, fast[w], color=BLUE, label="fast EMA (alpha 0.18)")
    a.plot(x, slow[w], color=ORANGE, label="slow EMA (alpha 0.04)")
    a.set_title("TOMATOES trend signal from the tutorial bot (day -2, ticks 3000-4500)")
    a.legend(loc="upper left", ncol=3)
    b.plot(x, trend[w], color=INK, linewidth=0.9)
    b.fill_between(x, trend[w], 0.75, where=trend[w] > 0.75, color=AQUA, alpha=0.35, label="trend > 0.75: cut asks")
    b.fill_between(x, trend[w], -0.75, where=trend[w] < -0.75, color=ORANGE, alpha=0.35, label="trend < -0.75: cut bids")
    b.axhline(0, color=MUTED, linewidth=0.6)
    b.set_ylabel("fast - slow")
    b.set_xlabel("tick")
    b.legend(loc="lower left", ncol=2)
    save(fig, "r0_ema_signal.png")


def r0_bootstrap():
    src_p = os.path.join(DATA, "round0", "prices_round_0_day_2.csv")  # holds day -2
    src_t = src_p.replace("prices", "trades")
    orig = read(0, "prices", 2)
    orig = orig[orig["product"] == "TOMATOES"].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(10, 4.5))
    with tempfile.TemporaryDirectory() as tmp:
        for seed in range(2):
            op, ot = os.path.join(tmp, f"p{seed}.csv"), os.path.join(tmp, f"t{seed}.csv")
            bootstrap_day(src_p, src_t, op, ot, method="block", block_len=100, seed=seed)
            b = pd.read_csv(op, sep=";")
            b = b[b["product"] == "TOMATOES"].reset_index(drop=True)
            ax.plot(b.index, b.mid_price, color=MUTED, linewidth=0.6, alpha=0.8,
                    label="block-bootstrap resamples (block 100)" if seed == 0 else None)
    ax.plot(orig.index, orig.mid_price, color=BLUE, linewidth=1.2, label="real day -2")
    ax.set_title("ProsperityBootstrap: TOMATOES day -2 vs two block-bootstrap days")
    ax.set_xlabel("tick")
    ax.set_ylabel("mid price")
    ax.legend(loc="upper left", ncol=2)
    ax.set_ylim(top=ax.get_ylim()[1] + 8)
    save(fig, "r0_bootstrap.png")


# ---------------------------------------------------------------- round 1

def r1_day_label_bug():
    files = [0, 1, 2]
    raw = pd.concat([read(1, "prices", d).assign(file=d) for d in files], ignore_index=True)
    raw = raw[(raw["product"] == PEPPER) & (raw.mid_price > 0)]
    fig, (a, b) = plt.subplots(2, 1, figsize=(10, 6.5), sharex=True)
    wrong = raw.sort_values(["file", "timestamp"]).reset_index(drop=True)
    a.plot(wrong.index, wrong.mid_price, color=ORANGE, linewidth=0.9)
    a.set_title("As the cleaning notebook stitched it: day = filename suffix (0, 1, 2)")
    right = raw.sort_values(["day", "timestamp"]).reset_index(drop=True)
    b.plot(right.index, right.mid_price, color=BLUE, linewidth=0.9)
    b.set_title("Ordered by the file's own day column (-2, -1, 0): one continuous trend")
    for ax, df, key in ((a, wrong, "file"), (b, right, "day")):
        for i, (_, g) in enumerate(df.groupby(key, sort=False)):
            if i:
                ax.axvline(g.index[0], color=MUTED, linestyle="--", linewidth=0.8)
            ax.text(g.index[0] + 300, 13050, f"{key} {g[key].iloc[0]}", color=MUTED, va="bottom")
        ax.set_ylabel("Pepper mid")
        ax.set_ylim(9800, 13300)
    b.set_xlabel("row (10,000 per day)")
    save(fig, "r1_day_label_bug.png")


def r1_products(p):
    ash = p[p["product"] == ASH].reset_index(drop=True)
    pep = p[p["product"] == PEPPER].reset_index(drop=True)
    fig, axes = plt.subplots(2, 2, figsize=(11, 6.5), gridspec_kw={"width_ratios": [3, 1]})
    (a, ah), (b, bh) = axes
    a.plot(ash.index, ash.mid_price, color=BLUE, linewidth=0.5)
    a.axhline(10000, color=INK, linestyle="--", linewidth=0.8)
    a.set_title("ASH_COATED_OSMIUM mid: pinned near 10,000 all round")
    ah.hist(ash.mid_price - 10000, bins=np.arange(-20.25, 18, 1.0), color=BLUE, orientation="horizontal")
    ah.set_title("mid - 10,000")

    t = np.arange(len(pep))
    slope, icpt = np.polyfit(t, pep.mid_price, 1)
    resid = pep.mid_price - (slope * t + icpt)
    b.plot(t, resid, color=ORANGE, linewidth=0.3, alpha=0.5)
    b.plot(t, resid.rolling(200, center=True).mean(), color=INK, linewidth=1, label="200-tick average")
    b.legend(loc="lower left")
    b.axhline(0, color=INK, linestyle="--", linewidth=0.8)
    b.set_title("INTARIAN_PEPPER_ROOT mid minus its straight-line trend (~1,000 per day)")
    b.set_xlabel("tick (3 days, chronological)")
    bh.hist(resid, bins=np.arange(-10.25, 10, 0.5), color=ORANGE, orientation="horizontal")
    bh.set_title("residual")
    save(fig, "r1_products.png")


def r1_variance_ratio(p):
    """E[(k-tick change)^2] / (k * E[(1-tick change)^2]), within each day. A random walk sits at 1."""
    ks = np.unique(np.logspace(0, np.log10(3000), 40).astype(int))
    fig, ax = plt.subplots(figsize=(9, 4.2))
    for prod, color in ((ASH, BLUE), (PEPPER, ORANGE)):
        g = p[p["product"] == prod].groupby("day").mid_price
        m1 = (g.diff() ** 2).mean()
        ax.plot(ks, [(g.diff(k) ** 2).mean() / (k * m1) for k in ks], color=color, marker="o", markersize=3,
                label=prod)
    ax.axhline(1, color=INK, linestyle="--", linewidth=0.8)
    ax.text(1.1, 1.05, "random walk", color=INK, va="bottom")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("horizon k (ticks, log)")
    ax.set_ylabel("variance ratio (log)")
    ax.set_title("Variance ratio: Ash mean-reverts at every horizon, Pepper's drift takes over past ~100 ticks")
    ax.legend(loc="upper left")
    save(fig, "r1_variance_ratio.png")


def r1_spreads(p):
    fig, ax = plt.subplots(figsize=(9, 4))
    for i, (prod, color) in enumerate(((ASH, BLUE), (PEPPER, ORANGE))):
        s = (p[p["product"] == prod].ask_price_1 - p[p["product"] == prod].bid_price_1).value_counts(normalize=True)
        s = s[s > 0.005].sort_index()
        ax.bar(s.index + (i - 0.5) * 0.4, s.values * 100, 0.38, color=color, label=prod)
    ax.set_xticks(range(2, 22))
    ax.set_xlabel("bot best ask - best bid (ticks)")
    ax.set_ylabel("% of ticks")
    ax.set_title("Bot spreads: room to quote inside them on both products")
    ax.legend()
    save(fig, "r1_spreads.png")


def r1_pepper_pnl():
    runs = {}
    runs["hold to the limit"] = backtest.run_backtest(baselines.BuyAndHoldTrader(), PEPPER)
    runs["regime switch (submitted)"] = backtest.run_backtest(traderModule.Trader(), PEPPER)
    old = traderModule.trendThreshold
    traderModule.trendThreshold = float("inf")
    runs["original market maker"] = backtest.run_backtest(traderModule.Trader(), PEPPER)
    traderModule.trendThreshold = old

    fig, (a, b) = plt.subplots(2, 1, figsize=(10, 6.5), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
    for (name, r), color in zip(runs.items(), (MUTED, BLUE, ORANGE)):
        x = r.index / 10000
        a.plot(x, r.pnl, color=color, label=f"{name}: {r.pnl.iloc[-1]:,.0f}")
        b.plot(x, r.position, color=color)
    a.set_title("Pepper: cumulative PnL (XIRECS), normal fills")
    a.legend(loc="upper left")
    b.set_ylabel("position")
    b.set_xlabel("day (corrected order)")
    for ax in (a, b):
        for d in (1, 2):
            ax.axvline(d, color=MUTED, linestyle="--", linewidth=0.8)
    save(fig, "r1_pepper_pnl.png")


def r1_ash_pnl():
    fig, (a, b) = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    for ax, fill, title in ((a, {}, "normal fills"), (b, STRESS, "stressed fills (50% size, strictly-through)")):
        mm = backtest.run_backtest(traderModule.Trader(), ASH, **fill)
        base = backtest.run_backtest(
            baselines.FixedValueMarketMaker(fairValue=10000, halfSpread=2, quoteSize=10), ASH, **fill)
        x = mm.index / 10000
        ax.plot(x, mm.pnl, color=BLUE, label=f"re-tuned MM + VR guard: {mm.pnl.iloc[-1]:,.0f}", linewidth=0.8)
        ax.plot(x, base.pnl, color=MUTED, label=f"fixed 10,000 +/- 2: {base.pnl.iloc[-1]:,.0f}", linewidth=0.8)
        for d in (1, 2):
            ax.axvline(d, color=MUTED, linestyle="--", linewidth=0.8)
        ax.set_title(f"Ash PnL, {title}")
        ax.set_xlabel("day")
        ax.legend(loc="upper left")
    save(fig, "r1_ash_pnl.png")


def r1_ash_null():
    # From `python checks.py` (README "Checks" table): shuffled-increment random-walk Ash, seeds 0-4.
    unguarded = [-211673, -217365, -191229, -90037, -204730]
    guarded = [-31314, -54852, 21612, 16935, 67535]
    base = [22141, 20998, 19794, 34765, 46115]
    x = np.arange(5)
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.bar(x - 0.27, unguarded, 0.25, color=ORANGE, label="re-tuned MM, no guard")
    ax.bar(x, guarded, 0.25, color=BLUE, label="re-tuned MM + VR guard")
    ax.bar(x + 0.27, base, 0.25, color=MUTED, label="fixed-value baseline")
    ax.scatter(x, [b - 30000 for b in base], marker="_", s=400, color=INK, zorder=3,
               label="declared floor (baseline - 30,000)")
    ax.axhline(0, color=INK, linewidth=0.6)
    ax.set_xticks(x, [f"seed {i}" for i in x])
    ax.set_ylabel("PnL on a random-walk Ash")
    ax.set_title("Null test: the guard cuts the blow-up but misses the floor on seeds 0 and 1")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2, fontsize=9)
    save(fig, "r1_ash_null.png")


def main():
    os.makedirs(IMG, exist_ok=True)
    p0 = chrono_prices(0, [1, 2])
    r0_overview(p0)
    r0_ema_signal(p0)
    r0_bootstrap()
    p1 = chrono_prices(1, [0, 1, 2])
    r1_day_label_bug()
    r1_products(p1)
    r1_variance_ratio(p1)
    r1_spreads(p1)
    r1_pepper_pnl()
    r1_ash_pnl()
    r1_ash_null()


if __name__ == "__main__":
    main()
