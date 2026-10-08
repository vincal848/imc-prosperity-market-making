"""Unit tests for trader.py's pricing logic, skew, and state round-trip."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from datamodel import Observation, OrderDepth, TradingState
import trader as traderModule


def make_depth(buys, sells):
    depth = OrderDepth()
    depth.buy_orders = dict(buys)
    depth.sell_orders = dict(sells)
    return depth


def test_microprice_weights_by_the_opposite_sides_volume():
    # bid 100 x 1, ask 102 x 3 -> heavier ask size pulls the price toward the bid.
    depth = make_depth({100: 1}, {102: -3})
    _bidPresent, _askPresent, _mid, microprice = traderModule.bookStats(depth, 0.0)
    assert microprice == 100.5


def test_microprice_falls_back_to_mid_when_volumes_are_equal():
    depth = make_depth({100: 5}, {102: -5})
    _bidPresent, _askPresent, mid, microprice = traderModule.bookStats(depth, 0.0)
    assert mid == 101.0
    assert microprice == 101.0


def test_choose_half_spread_picks_the_distance_that_maximises_rate_times_distance():
    state = traderModule.RollingState()
    state.tickWeight = 20.0
    state.deltaCounts = {3: 9.0}  # tradeRate(3) = 0.45 -> score 1.35, beats every other distance's 0
    assert traderModule.chooseHalfSpread(state) == 3


def test_choose_half_spread_falls_back_to_a_decaying_default_when_data_is_sparse():
    state = traderModule.RollingState()
    state.tickWeight = 5.0  # below the 20-tick warmup threshold
    # tradeRate(d) = 0.01 * exp(-0.2 d); score(d) = d * tradeRate(d) peaks at d=5 (1/0.2)
    assert traderModule.chooseHalfSpread(state) == 5


def _rolling_state_with_sigma(sigma, distance=2, rate=0.5):
    state = traderModule.RollingState()
    # 20 alternating +-sigma returns give a sample stdev of exactly sigma.
    for i in range(20):
        state.returns.append(sigma if i % 2 == 0 else -sigma)
    state.tickWeight = 20.0
    state.deltaCounts = {distance: rate * 20.0}
    return state


def test_inventory_skew_is_positive_for_a_long_position_and_negative_for_a_short_one():
    state = _rolling_state_with_sigma(sigma=1.0)
    halfSpread = traderModule.chooseHalfSpread(state)
    longSkew = traderModule.inventorySkew(10, state, horizon=1000, halfSpread=halfSpread)
    shortSkew = traderModule.inventorySkew(-10, state, horizon=1000, halfSpread=halfSpread)
    assert longSkew > 0
    assert shortSkew < 0
    assert shortSkew == -longSkew


def test_inventory_skew_is_zero_at_zero_position():
    state = _rolling_state_with_sigma(sigma=1.0)
    halfSpread = traderModule.chooseHalfSpread(state)
    assert traderModule.inventorySkew(0, state, horizon=1000, halfSpread=halfSpread) == 0.0


def test_inventory_skew_clamps_to_max_skew_ticks_for_a_large_position():
    state = _rolling_state_with_sigma(sigma=50.0)  # deliberately huge vol to force the clamp
    halfSpread = traderModule.chooseHalfSpread(state)
    skew = traderModule.inventorySkew(80, state, horizon=1000, halfSpread=halfSpread)
    assert skew == traderModule.maxSkewTicks


def test_rolling_state_to_dict_from_dict_round_trip():
    state = traderModule.RollingState()
    state.observe(mid=10000.0, microprice=10001.0, bidPresent=True, askPresent=True, tradePrices=[9998, 10003])
    state.observe(mid=10002.0, microprice=10002.5, bidPresent=True, askPresent=True, tradePrices=[10002])
    state.updateVolShock()

    restored = traderModule.RollingState.fromDict(state.toDict())

    assert list(restored.mids) == list(state.mids)
    assert list(restored.returns) == list(state.returns)
    assert restored.deltaCounts == state.deltaCounts
    assert restored.tickWeight == state.tickWeight
    assert restored.totalTicks == state.totalTicks
    assert restored.volShockTicks == state.volShockTicks
    assert restored.lastMid == state.lastMid
    assert restored.lastFairValue == state.lastFairValue


def test_fair_value_clamp_rounds_to_nearest_tick_not_truncated():
    # fairValue=10003.9 should clamp the bid ceiling at round(10003.9)=10004.
    # The bug fixed here used int(fairValue), which truncates to 10003 instead
    # (see legacy/TraderC1.py's docstring, defect 1). A large short position
    # pushes the reservation price up enough that the clamp actually binds,
    # so this test would fail against the truncating version of the clamp.
    state = traderModule.RollingState()
    state.lastFairValue = 10003.9
    state.tickWeight = 100.0  # past warmup so chooseHalfSpread/tradeRate are deterministic

    strategy = traderModule.AshStrategy()
    quotes = strategy.decide(state, mid=10003.9, position=-80, bidPresent=True, askPresent=True)

    bidQuotes = [price for price, quantity in quotes if quantity > 0]
    assert bidQuotes == [10004]


def test_strategy_never_requests_more_size_than_room_to_the_position_limit():
    state = traderModule.RollingState()
    state.lastFairValue = 10000.0
    state.tickWeight = 50.0

    strategy = traderModule.AshStrategy()
    for position in (-80, -79, -1, 0, 1, 79, 80):
        quotes = strategy.decide(state, mid=10000.0, position=position, bidPresent=True, askPresent=True)
        for _price, quantity in quotes:
            resulting = position + quantity
            assert -traderModule.positionLimit <= resulting <= traderModule.positionLimit


def test_vol_shock_widens_the_half_spread_and_shrinks_size():
    calm = traderModule.RollingState()
    calm.lastFairValue = 10000.0
    calm.tickWeight = 100.0
    calm.deltaCounts = {2: 50.0}
    calm.volShockTicks = 0

    shocked = traderModule.RollingState()
    shocked.lastFairValue = 10000.0
    shocked.tickWeight = 100.0
    shocked.deltaCounts = {2: 50.0}
    shocked.volShockTicks = 3  # at/above the volMultiplier threshold

    strategy = traderModule.AshStrategy()
    calmQuotes = strategy.decide(calm, mid=10000.0, position=0, bidPresent=True, askPresent=True)
    shockedQuotes = strategy.decide(shocked, mid=10000.0, position=0, bidPresent=True, askPresent=True)

    calmBid, calmAsk = sorted(price for price, _quantity in calmQuotes)
    shockedBid, shockedAsk = sorted(price for price, _quantity in shockedQuotes)
    assert (shockedAsk - shockedBid) > (calmAsk - calmBid)

    calmSize = max(abs(quantity) for _price, quantity in calmQuotes)
    shockedSize = max(abs(quantity) for _price, quantity in shockedQuotes)
    assert shockedSize < calmSize


def test_trader_run_never_proposes_an_order_that_alone_would_breach_the_position_limit():
    depth = make_depth({9999: 10}, {10001: 10})
    for symbol, position in (
        ("ASH_COATED_OSMIUM", 80),
        ("ASH_COATED_OSMIUM", -80),
        ("INTARIAN_PEPPER_ROOT", 80),
        ("INTARIAN_PEPPER_ROOT", -80),
    ):
        state = TradingState(
            traderData="",
            timestamp=0,
            listings={},
            order_depths={symbol: depth},
            own_trades={},
            market_trades={},
            position={symbol: position},
            observations=Observation({}, {}),
        )
        orders, _conversions, _traderData = traderModule.Trader().run(state)
        for order in orders.get(symbol, []):
            resulting = position + order.quantity
            assert -traderModule.positionLimit <= resulting <= traderModule.positionLimit


def feed(mids):
    state = traderModule.RollingState()
    for i, mid in enumerate(mids):
        state.observe(mid, mid, True, True, [])
    return state


def test_trend_target_follows_a_steady_drift_and_ignores_a_flat_series():
    n = 5000
    noise = [(-1) ** i for i in range(n)]
    assert feed([10000 + 0.2 * i + noise[i] for i in range(n)]).trendTarget() == traderModule.positionLimit
    assert feed([10000 - 0.2 * i + noise[i] for i in range(n)]).trendTarget() == -traderModule.positionLimit
    assert feed([10000 + noise[i] for i in range(n)]).trendTarget() == 0


def test_in_trend_mode_the_trader_crosses_the_book_to_rebuild_the_core():
    state = feed([10000 + 0.2 * i + (-1) ** i for i in range(5000)])
    quotes = traderModule.strategies["INTARIAN_PEPPER_ROOT"].decide(state, 11000.0, 0, True, True, 10999, 11001)
    assert quotes == [(11001, traderModule.positionLimit)]


def engagements(threshold, seeds=range(5), ticks=10000):
    """Number of zero-drift random-walk paths (Pepper-like vol) on which trend mode ever switches on."""
    import numpy as np
    old, traderModule.trendThreshold = traderModule.trendThreshold, threshold
    try:
        hits = 0
        for seed in seeds:
            walk = 10000 + np.cumsum(np.random.default_rng(seed).normal(0, 2.8, ticks))
            state = traderModule.RollingState()
            engaged = False
            for mid in walk:
                state.observe(mid, mid, True, True, [])
                engaged = engaged or state.trendTarget() != 0
            hits += engaged
        return hits
    finally:
        traderModule.trendThreshold = old


def test_trend_mode_does_not_engage_on_a_driftless_random_walk_but_the_old_threshold_did():
    assert engagements(traderModule.trendThreshold) == 0
    assert engagements(0.5) > 0  # the day-0-tuned 0.5 threshold failed the null


@pytest.mark.skipif(not os.path.exists(os.path.join(ROOT, "cleaned", "pepperPrices.csv")),
                    reason="cleaned/pepperPrices.csv not generated")
def test_trend_mode_does_not_engage_on_linearly_detrended_pepper():
    import backtest
    import checks
    prices, trades = backtest.load_product("INTARIAN_PEPPER_ROOT")
    flat, flatTrades = checks.detrended(prices, trades)
    records = backtest.Backtester(traderModule.Trader(), "INTARIAN_PEPPER_ROOT", prices=flat, trades=flatTrades).run()
    assert records["position"].abs().max() < 70


def _walk(seed, ticks, reversion):
    """Mid path with per-tick noise sd 2.8; reversion=0 is a driftless random walk, >0 an OU series around 10000."""
    import numpy as np
    rng, x, out = np.random.default_rng(seed), 0.0, []
    for _ in range(ticks):
        x += -reversion * x + rng.normal(0, 2.8)
        out.append(10000 + x)
    return out


def test_variance_ratio_guard_engages_on_a_planted_mean_reverting_series_and_not_on_a_random_walk():
    ash = traderModule.strategies["ASH_COATED_OSMIUM"]
    lag, threshold = ash.guardLag, ash.guardThreshold
    assert traderModule.varianceRatioZ(_walk(0, 1000, 0.3)[-500:], lag) < -threshold
    walks = [_walk(seed, 5000, 0.0) for seed in range(4)]
    zs = [traderModule.varianceRatioZ(w[end - 500:end], lag) for w in walks for end in range(500, 5000, 25)]
    assert sum(z < -threshold for z in zs) / len(zs) <= 0.02


def _cheap_ask_orders(strategy, mids):
    state = feed(mids)
    fair = round(state.lastFairValue)
    return fair, strategy.decide(state, fair, 0, True, True, bestBid=fair - 9, bestAsk=fair - 5)


def test_disengaged_guard_stops_taking_the_book_and_the_flat_fallback_unwinds():
    ash = traderModule.AshStrategy()
    fair, orders = _cheap_ask_orders(ash, _walk(1, 800, 0.3))
    assert (fair - 5, 20) in orders  # mean-reverting: takes the cheap ask
    fair, orders = _cheap_ask_orders(ash, _walk(1, 800, 0.0))
    assert (fair - 5, 20) not in orders  # random walk: passive quoting only
    ash.guardFlat = True
    state = feed(_walk(1, 800, 0.0))
    assert ash.decide(state, 10000.0, 30, True, True, bestBid=9999, bestAsk=10001) == [(9999, -20)]
    assert ash.decide(state, 10000.0, -5, True, True, bestBid=9999, bestAsk=10001) == [(10001, 5)]


@pytest.mark.skipif(not os.path.exists(os.path.join(ROOT, "cleaned", "ashPrices.csv")),
                    reason="cleaned/ashPrices.csv not generated")
def test_guarded_ash_mm_loses_far_less_than_unguarded_on_shuffled_increment_ash():
    import backtest
    import checks
    prices, trades = checks.random_walked(*backtest.load_product("ASH_COATED_OSMIUM"), seed=0)

    def pnl(bot):
        return backtest.Backtester(bot, "ASH_COATED_OSMIUM", prices=prices, trades=trades).run()["pnl"].iloc[-1]

    # Regression bound, NOT the declared criterion (>= baseline - 30,000, which the guard misses: see README).
    # The unguarded MM lost 211,673 here; the baseline gained 22,141.
    assert pnl(traderModule.Trader()) >= -60000
