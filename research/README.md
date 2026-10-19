# Research notebooks

Exploratory work from the competition, kept for history. The maintained code lives at the repo root.

**Start with [WALKTHROUGH.md](WALKTHROUGH.md)**, a round-by-round account of the approach, with charts.

- `round0/`: tutorial round (EMERALDS, TOMATOES). `ProsperityBootstrap` resamples a day in blocks;
  `prosperity_backtest_v1`–`v4` are successive backtest iterations.
- `round1/`: `clean_round1_data` splits the raw round 1 files per product (its forced `day` column is
  the source of the day-ordering bug; superseded by `prepare_data.py`), `Research` is a signal-hunting
  toolkit for Ash, and `dashboard` is the plotting dashboard.
- `data/`: the public IMC Prosperity price and trade exports for both rounds, unmodified.
- `img/` and `make_charts.py`: the walkthrough's charts and the script that regenerates them.

The notebooks expect their CSVs in the working directory; copy them in from `data/`.
