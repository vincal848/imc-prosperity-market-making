import csv
import random
from collections import defaultdict
from pathlib import Path


def load_price_rows(path):
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            rows.append(dict(row))
    return rows


def load_trade_rows(path):
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            rows.append(dict(row))
    return rows


def group_rows_by_timestamp(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[int(row["timestamp"])].append(row)
    return dict(sorted(grouped.items()))


def extract_ordered_timestamps(grouped):
    return sorted(grouped.keys())


def make_blocks_from_grouped(grouped, block_len):
    ts_list = extract_ordered_timestamps(grouped)
    blocks = []

    if len(ts_list) < block_len:
        return [ts_list[:]]

    for start in range(0, len(ts_list) - block_len + 1):
        blocks.append(ts_list[start:start + block_len])

    return blocks


def stationary_bootstrap_indices(n, avg_block_len, rng):
    indices = []
    i = rng.randrange(n)

    while len(indices) < n:
        indices.append(i)
        if rng.random() < 1.0 / avg_block_len:
            i = rng.randrange(n)
        else:
            i = (i + 1) % n

    return indices


def reindex_price_rows(grouped_price_rows, sampled_ts, timestamp_step=100):
    out_rows = []
    new_ts = 0

    for old_ts in sampled_ts:
        rows = grouped_price_rows[old_ts]
        for row in rows:
            new_row = dict(row)
            new_row["timestamp"] = str(new_ts)
            out_rows.append(new_row)
        new_ts += timestamp_step

    return out_rows


def reindex_trade_rows(grouped_trade_rows, sampled_ts, timestamp_step=100):
    out_rows = []
    new_ts = 0

    for old_ts in sampled_ts:
        rows = grouped_trade_rows.get(old_ts, [])
        for row in rows:
            new_row = dict(row)
            new_row["timestamp"] = str(new_ts)
            out_rows.append(new_row)
        new_ts += timestamp_step

    return out_rows


def write_rows(path, rows, fieldnames):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def bootstrap_day(
    price_path,
    trade_path,
    out_price_path,
    out_trade_path,
    method="block",
    block_len=100,
    avg_block_len=100,
    seed=42
):
    rng = random.Random(seed)

    price_rows = load_price_rows(price_path)
    trade_rows = load_trade_rows(trade_path)

    grouped_price = group_rows_by_timestamp(price_rows)
    grouped_trade = group_rows_by_timestamp(trade_rows)

    ts_list = extract_ordered_timestamps(grouped_price)
    n_ts = len(ts_list)

    if method == "block":
        sampled_ts = []
        blocks = make_blocks_from_grouped(grouped_price, block_len)

        while len(sampled_ts) < n_ts:
            block = rng.choice(blocks)
            sampled_ts.extend(block)

        sampled_ts = sampled_ts[:n_ts]

    elif method == "stationary":
        idx = stationary_bootstrap_indices(n_ts, avg_block_len, rng)
        sampled_ts = [ts_list[i] for i in idx]

    else:
        raise ValueError("method must be 'block' or 'stationary'")

    boot_price_rows = reindex_price_rows(grouped_price, sampled_ts)
    boot_trade_rows = reindex_trade_rows(grouped_trade, sampled_ts)

    price_fieldnames = list(price_rows[0].keys()) if price_rows else []
    trade_fieldnames = list(trade_rows[0].keys()) if trade_rows else []

    write_rows(out_price_path, boot_price_rows, price_fieldnames)
    write_rows(out_trade_path, boot_trade_rows, trade_fieldnames)


def bootstrap_many(
    price_files,
    trade_files,
    out_dir,
    n_samples=20,
    method="block",
    block_len=100,
    avg_block_len=100,
    seed=42
):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    created = []
    base_rng = random.Random(seed)

    for sample_idx in range(n_samples):
        sample_seed = base_rng.randint(0, 10**9)

        sample_price_files = []
        sample_trade_files = []

        for day_idx, (pf, tf) in enumerate(zip(price_files, trade_files), start=1):
            out_price = out_dir / f"boot_prices_sample_{sample_idx:03d}_day_{day_idx}.csv"
            out_trade = out_dir / f"boot_trades_sample_{sample_idx:03d}_day_{day_idx}.csv"

            bootstrap_day(
                price_path=pf,
                trade_path=tf,
                out_price_path=out_price,
                out_trade_path=out_trade,
                method=method,
                block_len=block_len,
                avg_block_len=avg_block_len,
                seed=sample_seed + day_idx
            )

            sample_price_files.append(str(out_price))
            sample_trade_files.append(str(out_trade))

        created.append({
            "sampleIdx": sample_idx,
            "priceFiles": sample_price_files,
            "tradeFiles": sample_trade_files
        })

    return created
