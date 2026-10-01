"""CLI: python run.py <backtest|stats|compare> ..."""
import argparse
import os

import pandas as pd

import backtest
import baselines
import trader as traderModule

ROOT = os.path.dirname(os.path.abspath(__file__))
CLEANED_DIR = os.path.join(ROOT, "cleaned")

PRODUCTS = ["ASH_COATED_OSMIUM", "INTARIAN_PEPPER_ROOT"]


def cmd_backtest(args):
    products = PRODUCTS if args.product is None else [args.product]
    for product in products:
        records = backtest.run_backtest(traderModule.Trader(), product, args.days)
        perDay = backtest.day_pnl(records)
        print(f"\n{product}")
        print(f"  ticks: {len(records)}  final position: {records['position'].iloc[-1]}  "
              f"total pnl: {records['pnl'].iloc[-1]:.2f}")
        print("  per-day pnl:")
        for day, pnl in perDay.items():
            print(f"    day {day}: {pnl:.2f}")


def cmd_stats(args):
    prefix = {"ASH_COATED_OSMIUM": "ash", "INTARIAN_PEPPER_ROOT": "pepper"}
    products = PRODUCTS if args.product is None else [args.product]
    for product in products:
        prices = pd.read_csv(os.path.join(CLEANED_DIR, f"{prefix[product]}Prices.csv"))
        summary = prices.groupby("day")["mid_price"].agg(["min", "max", "mean", "std", "count"])
        print(f"\n{product} mid price by day (day 0 = earliest, day 2 = latest):")
        print(summary)


BASELINES = {
    "ASH_COATED_OSMIUM": lambda: baselines.FixedValueMarketMaker(fairValue=10000, halfSpread=2, quoteSize=10),
    "INTARIAN_PEPPER_ROOT": lambda: baselines.BuyAndHoldTrader(),
}


def cmd_compare(args):
    products = PRODUCTS if args.product is None else [args.product]
    for product in products:
        rebuilt = backtest.run_backtest(traderModule.Trader(), product, args.days)
        base = backtest.run_backtest(BASELINES[product](), product, args.days)

        print(f"\n{product}")
        print(f"  rebuilt trader   total pnl: {rebuilt['pnl'].iloc[-1]:.2f}  "
              f"final position: {rebuilt['position'].iloc[-1]}")
        print(f"  trivial baseline total pnl: {base['pnl'].iloc[-1]:.2f}  "
              f"final position: {base['position'].iloc[-1]}")


def main():
    parser = argparse.ArgumentParser(description="IMC Prosperity Round 1 trader tooling.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backtestParser = subparsers.add_parser("backtest", help="Replay trader.py against cleaned/ order books.")
    backtestParser.add_argument("--product", choices=PRODUCTS, default=None)
    backtestParser.add_argument("--days", type=int, nargs="*", default=None)
    backtestParser.set_defaults(func=cmd_backtest)

    statsParser = subparsers.add_parser("stats", help="Per-day price stats from cleaned/.")
    statsParser.add_argument("--product", choices=PRODUCTS, default=None)
    statsParser.set_defaults(func=cmd_stats)

    compareParser = subparsers.add_parser("compare", help="Rebuilt trader vs a trivial per-product baseline.")
    compareParser.add_argument("--product", choices=PRODUCTS, default=None)
    compareParser.add_argument("--days", type=int, nargs="*", default=None)
    compareParser.set_defaults(func=cmd_compare)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
