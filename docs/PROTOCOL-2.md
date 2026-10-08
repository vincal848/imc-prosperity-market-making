# Evaluation protocol 2 (declared before any of these variants ran)

Follows `PROTOCOL.md` (19 variants so far). Same rules: tune on **day 0 only**,
score days 1 and 2 **once**, count every variant. Variants below are new, on top
of the 19, so the running total is 19 + (count printed by `walkforward.py`).

## Part 1: calibrated regime switch (Pepper -> hold, Ash -> MM)

- Statistic changes from a fixed 500-tick window to an **expanding-window**
  t-stat, `t = (mid - first mid) / (sigma * sqrt(ticks))`, because a fixed
  window short enough to react (|t| ~ 0.7 at 500 ticks on real Pepper) cannot
  reach a significance level. Cost: detection takes ~3,000 ticks on day 0.
- Threshold candidates: **2.0** (fixed rule) and **cal**, the 99th percentile
  of |t| (after a 500-tick warm-up) on the linearly detrended day-0 Pepper
  series, floored at 2.0. Overlay band candidates: 0 and 10. 4 variants,
  chosen by day-0 Pepper + Ash PnL.
- The null check becomes a test: detrended Pepper must never engage the trend
  mode; it must fail with the old 0.5 threshold.
- If the calibrated mode adds nothing over plain hold-to-limit, simplify.

## Part 2: Ash market maker under the stressed fill model

The stressed model (passive fills at 50% of printed quantity, strictly-through
prints only) is treated as the realistic one. The MM and the fixed-value
baseline are both tuned/evaluated under it on day 0; days 1-2 are reported
once under BOTH fill models. Coordinate descent, simplest first, each run is a
variant, selection by stressed day-0 Ash PnL, ties keep the earlier setting:

1. half-spread: learned (current) vs fixed in {1, 2, 3, 4, 6}
2. inventory-skew scale in {0, 0.5, 1}
3. slow-mean anchor weight in {0, 0.5, 1} (fair = microprice + w * (mean of last
   500 mids - microprice); data-driven, no hard-coded 10000)
4. take-when-mispriced edge in {off, 2, 4, 6} against the anchored fair value
5. quote size in {10, 20}

"Beats the baseline" = higher Ash PnL than the fixed-value MM baseline on both
test days under both fill models. Otherwise the README says so.

## Amendment (committed before any protocol-2 variant ran)

Measured while writing the code, on signal-free data only: the detrended
day-0 Pepper series is bounded, so its |t| p99 is 0.06 and `cal` collapses to
the 2.0 floor. But on a simulated i.i.d. random-walk null (30,000 ticks, 1,000
seeded paths) |t| > 2 is hit at some tick 40% of the time, so 2.0 is not a null
the regime switch can claim to pass. Added:

- a third threshold, **rw99 = 3.7**, the 99th percentile of the running-max |t|
  of that random-walk null;
- an eligibility rule: a threshold whose false-engagement rate on the random-walk
  null exceeds 5% is **ineligible** for selection, whatever its day-0 PnL.
  Ties among eligible variants keep the earlier (overlay 0).

Total new Part-1 variants: 3 thresholds x 2 overlays = 6.
