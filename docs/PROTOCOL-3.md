# Evaluation protocol 3 (declared before any of these variants ran)

Follows `PROTOCOL.md` (19 variants) and `PROTOCOL-2.md` (20 more), 39 so far.
Same rules: tune on **day 0 only**, score days 1 and 2 **once**, count every
variant. Variants below are new, on top of the 39.

**Why.** The re-tuned Ash market maker beats the fixed-value baseline on days
1-2, but on a shuffled-increment random-walk Ash it loses 211,673 (baseline
+22,141). Its edge is the bet that Ash mean-reverts (anchor to the 500-mid
mean, take the book 2 ticks through it); the drift leg of the regime switch
only tests for drift.

## The guard (second leg of the regime switch, Ash only)

- Statistic: Lo-MacKinlay variance ratio of mid changes over the last 500
  mids (the existing rolling window), overlapping k-step changes, zero-mean
  (Ash has no drift): `VR(k) = var_k / (k * var_1)`, standardised with the
  homoskedastic asymptotic variance `2(2k-1)(k-1) / (3kn)` into `z`.
- The anchor and the take-the-book rule are **engaged only while
  `z < -c_k`**, i.e. VR significantly below 1. Before 500 mids exist, `z = 0`
  (not engaged).
- Calibration `c_k` on signal-free data only: 200 seeded driftless Gaussian
  random walks x 5,000 ticks, sigma = std of Ash's day-0 mid changes, `z`
  evaluated every 25 ticks after the 500-tick warm-up. **Declared max
  false-engagement rate: 1% of ticks.** `c_k` = minus the 1st percentile of
  `z`. A threshold that exceeds 1% on a second independent seed set is
  ineligible. The calibration is run and committed before any variant is scored.
- When not engaged, the fallback (declared up front, both tried):
  - `passive`: same market maker (half spread, skew, size) around the
    microprice with anchor 0 and no taking (the fixed-value-style passive
    quoting, but data-driven);
  - `flat`: no new quotes; unwind the position to 0 by crossing the book.
- Pepper is untouched; the drift leg and its 3.7 threshold are unchanged.

## Variants (4 new, total 43)

k in {5, 20} x fallback in {passive, flat}, in that order
(5-passive, 5-flat, 20-passive, 20-flat). Selection by **stressed day-0 Ash
PnL**, ties keep the earlier. The previous day-0 pick (width 3, skew 1,
anchor 1, take edge 2, size 20) is held fixed; the guard is the only new
dimension.

## Success criteria (declared before running)

1. Real Ash, days 1-2, **both fill models**: the guarded MM still beats the
   fixed-value baseline on both days (it may give back some of the unguarded
   edge; the give-back is reported).
2. Shuffled-increment random-walk Ash (`checks.random_walked`, seeds 0-4,
   normal fills): on every seed the guarded MM's PnL is at least the
   fixed-value baseline's PnL on the same path **minus 30,000**. (Unguarded:
   -211,673 vs +22,141 on seed 0.)
3. The drift leg's existing nulls still pass (random-walk engagement test,
   detrended Pepper), and Pepper results are unchanged.

Tests: the random-walk Ash test must fail with the guard switched off; a
planted mean-reverting OU series must engage it, a random walk must not
(false-engagement share <= 2% in the test).

If the guard costs all of the real-day edge, the README says so. Days 1-2 are
not used to pick or tweak anything; if a criterion fails it is reported as
failed, not retuned in this PR.

## Calibration result (committed before any variant was scored)

`python walkforward.py calibrate`: c_5 = 2.29 (0.8% false engagement on the
independent seed set), c_20 = 1.979 (1.0%). Both within the declared 1% (the
eligibility check allows up to 2x on sampling noise).
