"""Honest checks on the day-0-selected configuration (see README): null, placebo, fill stress.

Usage: python checks.py
"""
import backtest
import baselines
import trader
from walkforward import ASH, PEPPER, baseline

import numpy as np

PRICE_COLS = [f"{side}_price_{k}" for side in ("bid", "ask") for k in (1, 2, 3)]


def detrended(prices):
    """Pepper with its linear trend (fit on mid, whole sample) subtracted, kept on the integer tick grid."""
    shift = np.polyval(np.polyfit(np.arange(len(prices)), prices["mid_price"], 1), np.arange(len(prices)))
    shift = np.round(shift - shift[0])
    out = prices.copy()
    for col in PRICE_COLS + ["mid_price"]:
        out[col] = out[col] - shift
    return out, shift


def negated(prices, trades):
    """Mirror prices around their first mid: bids become asks and vice versa, trade prices flip."""
    centre = 2 * round(prices["mid_price"].iloc[0])
    out, flipped = prices.copy(), trades.copy()
    for k in (1, 2, 3):
        for field in ("price", "volume"):
            out[f"bid_{field}_{k}"], out[f"ask_{field}_{k}"] = prices[f"ask_{field}_{k}"], prices[f"bid_{field}_{k}"]
        out[f"bid_price_{k}"] = centre - out[f"bid_price_{k}"]
        out[f"ask_price_{k}"] = centre - out[f"ask_price_{k}"]
    out["mid_price"] = centre - prices["mid_price"]
    flipped["price"] = centre - trades["price"]
    return out, flipped


def engaged(prices, trades) -> float:
    """Fraction of ticks the trader's trend mode is on (position-independent: re-run the t-stat)."""
    bt = backtest.Backtester(trader.Trader(), PEPPER, prices=prices, trades=trades)
    records = bt.run()
    return float((records["position"].abs() >= 70).mean()), records


def main() -> None:
    prices, trades = backtest.load_product(PEPPER)
    for label, (p, t) in {
        "real": (prices, trades),
        "null (detrended)": (detrended(prices)[0], trades),
        "placebo (negated)": negated(prices, trades),
    }.items():
        share, records = engaged(p, t)
        base = backtest.Backtester(baselines.BuyAndHoldTrader(), PEPPER, prices=p, trades=t).run()
        print(f"{label:20s} strategy pnl {records['pnl'].iloc[-1]:>10.0f} final pos {records['position'].iloc[-1]:>4}"
              f" share|pos|>=70 {share:.2f} min pos {records['position'].min()} | hold-to-limit pnl {base['pnl'].iloc[-1]:.0f}")
    stress = dict(passiveFillFraction=0.5, strictTradeThrough=True)
    for product in (PEPPER, ASH):
        strat = list(backtest.day_pnl(backtest.run_backtest(trader.Trader(), product, [0, 1, 2], **stress)))
        print("stress", product, "strategy", strat, "baseline", baseline(product, [0, 1, 2], **stress))


if __name__ == "__main__":
    main()
