# Background

## IMC Prosperity Round 1 (2026)

[IMC Prosperity](https://prosperity.imc.com/) is an annual trading
competition. Round 1 of the 2026 edition was a pure market-making problem:
two synthetic products, ASH_COATED_OSMIUM ("Ash") and INTARIAN_PEPPER_ROOT
("Pepper"), traded in currency XIRECS, position limit 80 per product, no
conversions. A submission is a single Python file exposing `Trader.run(state)
-> (orders, conversions, traderData)`, where `state` is an IMC-provided
`TradingState` (order book depth, recent trades, position, and a string you
control for persisting state across ticks) and `datamodel.py` is provided by
the competition engine at submission time, not published as a package.

This repo is five generations of that Trader, written over the course of the
round (see `git log` on `main` before the rebuild), from a hardcoded-fair-
value quoter through a z-score mean reversion bot to TraderC1, an
Avellaneda-Stoikov-flavored market maker with an empirically fit half spread.
`trader.py` is TraderC1 cleaned up; the rest are kept in `legacy/`.

## The day-ordering bug

`cleaned/*.csv` holds three days of order book snapshots and trades per
product (10,000 ticks/day, 100ms apart). The script that produced them is
lost -- see `prepare_data.py`'s docstring for the full reasoning -- but the
`day` column it wrote (0, 1, 2) turned out to be backwards:

| raw day | Pepper mid range | chronological position |
|---|---|---|
| 0 | 12000-13000 | **latest** |
| 1 | 11000-12000 | middle |
| 2 | 10000-11000 | **earliest** |

`Background_and_Research/PepperGraph.png`, generated before this fix, shows
the effect directly: the "Reference Price" trace is three disconnected
rising sawtooth segments (13000 -> drop to 11000 -> rise to 12000 -> drop to
10000 -> rise to 11000) instead of one continuous line. The commit that added
that screenshot is literally titled "notice drop in the day rollover via vol
adjustment" -- the original author saw the artifact and attributed it to a
market effect, not a labeling bug in their own pipeline.

Pepper trends up roughly 1000 XIRECS/day essentially linearly for the whole
round (see `docs/img/pepper_price_and_pnl.png`, and `python run.py stats`).
Reversing the day label (`prepare_data.DAY_MAP = {0: 2, 1: 1, 2: 0}`) turns
the three segments into one continuous rising line from 10000 to 13000, which
is the chronologically sensible reading and matches IMC's own day-labeling
convention for Prosperity data (files are provided as day -2, -1, 0, with 0
the most recent -- consistent with someone zipping the three source files
with `range(3)` and never reversing the result).

Ash does not show this artifact -- it mean-reverts around 10000 all three
days (`Background_and_Research/AshGraph.png`) -- which is additional
evidence this is a labeling bug specific to how the files were concatenated,
not a real feature of either market.

## Why Pepper's trend matters for the strategy comparison

`trader.py`'s PepperStrategy already contains a (deliberately bounded) drift
fair-value shift, since TraderC1's author presumably noticed the trend
intraday even working from the mislabeled data. But a bounded, mean-
reverting-flavored market maker is structurally a poor fit for an asset that
is trending almost deterministically for the entire round: see the README's
Results section for the actual numbers -- a trivial buy-and-hold baseline
outearns the rebuilt symmetric market maker on Pepper by a wide margin, while
the market maker wins comfortably on the mean-reverting Ash.
