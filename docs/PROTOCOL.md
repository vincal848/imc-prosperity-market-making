# Evaluation protocol (declared before any new strategy was run)

Data is three days, one continuous Pepper trend, so every claim is weak. The
protocol below is fixed in writing first; deviations get listed in the README.

1. **Baselines come first.** Hold-to-limit for Pepper (buy at the best ask
   every tick until position 80), fixed-fair-value MM (10000 +/- 2) for Ash.
   Both corrected numbers are recorded per day before any new strategy runs.
2. **Walk-forward by day.** Anything tunable is tuned on **day 0 only**
   (`days=[0]`). Exactly one chosen configuration is then run through days 0-2
   continuously (state and position carry over, as live) and scored on **days
   1 and 2**, once. Days 1 and 2 are never used to pick, tweak or drop a variant.
3. **Variant count.** Every configuration evaluated on day 0 is a variant, and
   `walkforward.py` prints the count. The README reports it next to the result.
4. **Beating the baseline** means higher PnL than the baseline on BOTH test
   days, under the unstressed fill model, and still higher (or equal within the
   baseline's own stressed result) under the stressed fill model.
5. **Checks (the result must survive these or it is not reported as a win):**
   - null: linearly detrended Pepper -> the trend mode must not engage;
   - placebo: time-reversed / negated Pepper -> the strategy goes short and
     does not blow up (no loss beyond the baseline's loss on the same data);
   - fill stress: passive fills at 50% of printed quantity and only on strictly
     through prints.
6. If nothing beats the baseline out of sample, the README says so with numbers.
