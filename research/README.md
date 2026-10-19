# Research notebooks

Exploratory work from the competition, kept for history. The maintained code lives at the repo root.

- `round0/`: tutorial round. `ProsperityBootstrap` resamples the round 0 price data; `prosperity_backtest_v1`–`v4` are successive backtest iterations.
- `round1/`: `clean_round1_data` splits the raw round 1 files per product (superseded by `prepare_data.py`), `Research` is product analysis, and `dashboard` is the plotting dashboard.

The notebooks expect the raw `prices_round_*` / `trades_round_*` CSVs in the working directory. Those CSVs aren't committed here.
