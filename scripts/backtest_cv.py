"""
Cross-Validation 백테스트 (Rolling fold + Reverse fold)

목적: HMM regime strategy가 시기에 따라 robust한지 검증.

Fold 정의:
- Original: Train 2017-2021 / Test 2022-2026 (기준선)
- Fold-1: Train 2017-2020 / Test 2021 (단기 검증)
- Fold-2: Train 2018-2021 / Test 2022-2023 (강세 초입)
- Fold-3: Train 2019-2022 / Test 2024-2026 (최근)
- Fold-R: Train 2019-2026 / Test 2016-2018 (역방향, 약세 2018 포함)

각 fold:
1. HMM 학습 (BIC 기반 n_regimes 선택, 4로 고정 가능)
2. Train sector winners 결정 (forward 20d return top-N)
3. Test 기간 strategy backtest (top3_regime_change, stay-invested)
4. KOSPI 벤치마크 비교 (Sharpe, alpha, MDD)

실행:
  python scripts/backtest_cv.py
"""

import json
import pickle
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore")

from hmmlearn.hmm import GaussianHMM  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent
ART_DIR = BASE_DIR / "scripts" / "ml_artifacts"
SECTOR_PANEL = ART_DIR / "sector_panel.parquet"
KOSPI_HISTORY = BASE_DIR / "public" / "data" / "kospi-history.json"
OUT_JSON = ART_DIR / "backtest_cv_results.json"

# Fixed (cycle_hmm.py와 동일)
N_REGIMES = 4
N_SEEDS = 3
MAX_ITER = 200
COV_TYPE = "full"
TC = 0.005
FEAT_COLS = ["vol_20d", "ret_20d", "dispersion_20d", "flow_z_5d"]

# Folds: (name, train_start, train_end, test_start, test_end)
FOLDS = [
    ("Original",   None,        "2021-12-31", "2022-01-01", None),
    ("Fold-1 (2021 test)",    None,        "2020-12-31", "2021-01-01", "2021-12-31"),
    ("Fold-2 (2022-23 test)", "2018-01-01","2021-12-31", "2022-01-01", "2023-12-31"),
    ("Fold-3 (2024-26 test)", "2019-01-01","2022-12-31", "2023-01-01", None),
    ("Fold-R (2016-18 test)", "2019-01-01", None,        None,         "2018-12-31"),  # 역방향
]

TOP_N = 3


# ──────────────────────────────────────────────────────────
# Feature engineering (cycle_hmm.py와 동일)
# ──────────────────────────────────────────────────────────

def build_features(sector_panel):
    ret_pivot = sector_panel.pivot(index="date", columns="sector", values="sector_ret")
    mcap_pivot = sector_panel.pivot(index="date", columns="sector", values="mcap_sum")
    weighted_ret = (ret_pivot * mcap_pivot).sum(axis=1) / mcap_pivot.sum(axis=1)
    weighted_ret = weighted_ret.replace([np.inf, -np.inf], np.nan)

    vol_20d = weighted_ret.rolling(20).std() * np.sqrt(250)
    ret_20d = (1 + weighted_ret).rolling(20).apply(np.prod, raw=True) - 1
    dispersion_20d = ret_pivot.std(axis=1).rolling(20).mean()

    flow_pivot_f = sector_panel.pivot(index="date", columns="sector", values="foreign_sum")
    flow_pivot_i = sector_panel.pivot(index="date", columns="sector", values="inst_sum")
    mkt_flow = flow_pivot_f.sum(axis=1) + flow_pivot_i.sum(axis=1)
    flow_5d = mkt_flow.rolling(5).sum()
    flow_z = (flow_5d - flow_5d.rolling(252).mean()) / flow_5d.rolling(252).std()

    df = pd.DataFrame({
        "vol_20d": vol_20d, "ret_20d": ret_20d,
        "dispersion_20d": dispersion_20d, "flow_z_5d": flow_z,
        "mkt_ret": weighted_ret,
    }).dropna()
    return df, ret_pivot


def fit_hmm(X_train, n_regimes=N_REGIMES, n_seeds=N_SEEDS):
    """Best seed로 HMM 학습 (LL 기준)"""
    best = None
    for seed in range(n_seeds):
        try:
            m = GaussianHMM(
                n_components=n_regimes, covariance_type=COV_TYPE,
                n_iter=MAX_ITER, random_state=seed, tol=1e-4,
            )
            m.fit(X_train)
            ll = m.score(X_train)
            if best is None or ll > best[1]:
                best = (m, ll, seed)
        except Exception:
            continue
    return best[0] if best else None


def compute_train_winners(regimes_train, ret_pivot_train, dates_train, n_regimes, forward_window=20):
    cumret = (1 + ret_pivot_train).rolling(forward_window).apply(np.prod, raw=True) - 1
    forward = cumret.shift(-forward_window)
    winners = {}
    for r in range(n_regimes):
        regime_dates = [d for d, rg in zip(dates_train, regimes_train) if rg == r]
        if not regime_dates:
            continue
        regime_forward = forward.loc[regime_dates].dropna(how="all")
        if regime_forward.empty:
            continue
        means = regime_forward.mean()
        winners[r] = means[means > 0].sort_values(ascending=False).index.tolist()
    return winners


def run_backtest(regimes_test, ret_pivot_test, dates_test, kospi_aligned, train_winners, top_n=TOP_N, tc=TC):
    """top3_regime_change strategy (stay-invested)"""
    cash = 1.0
    positions = []
    n_trades = 0
    pv_log = []
    prev_regime = -1

    for i, date in enumerate(dates_test):
        cur_regime = regimes_test[i]
        for pos in positions:
            sec_ret = ret_pivot_test.loc[date, pos["sector"]] if pos["sector"] in ret_pivot_test.columns else 0
            if pd.isna(sec_ret):
                sec_ret = 0
            pos["weight"] *= (1 + sec_ret)

        regime_changed = (cur_regime != prev_regime) and i > 0
        new_positions = []
        for pos in positions:
            if regime_changed:
                cash += pos["weight"] * (1 - tc / 2)
                n_trades += 1
            else:
                new_positions.append(pos)
        positions = new_positions

        if not positions:
            top_sectors = train_winners.get(cur_regime, [])[:top_n]
            if top_sectors and cash > 0:
                ew = (cash * (1 - tc / 2)) / len(top_sectors)
                for sec in top_sectors:
                    positions.append({"sector": sec, "weight": ew})
                cash = 0
                n_trades += len(top_sectors)

        pv = cash + sum(p["weight"] for p in positions)
        pv_log.append({"date": str(date), "pv": pv})
        prev_regime = cur_regime

    for pos in positions:
        cash += pos["weight"] * (1 - tc / 2)

    pv_series = pd.DataFrame(pv_log).set_index("date")["pv"]
    daily_ret = pv_series.pct_change().dropna()
    n_days = len(daily_ret)
    if n_days == 0:
        return None
    cum_ret = pv_series.iloc[-1] - 1
    ann_ret = (1 + cum_ret) ** (250 / n_days) - 1
    ann_vol = daily_ret.std() * np.sqrt(250)
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0
    cum_pv = pv_series.values
    running_max = np.maximum.accumulate(cum_pv)
    drawdown = (cum_pv - running_max) / running_max
    mdd = drawdown.min()

    # Benchmark
    bench_ret = kospi_aligned
    bench_cum = (1 + bench_ret).cumprod().iloc[-1] - 1
    bench_ann_vol = bench_ret.std() * np.sqrt(250)
    bench_ann_ret = (1 + bench_cum) ** (250 / len(bench_ret)) - 1
    bench_sharpe = bench_ann_ret / bench_ann_vol if bench_ann_vol > 0 else 0

    return {
        "n_days": n_days,
        "cum_return": float(cum_ret),
        "annualized_return": float(ann_ret),
        "sharpe": float(sharpe),
        "max_drawdown": float(mdd),
        "n_trades": int(n_trades),
        "benchmark_cum": float(bench_cum),
        "benchmark_ann": float(bench_ann_ret),
        "benchmark_sharpe": float(bench_sharpe),
        "alpha": float(ann_ret - bench_ann_ret),
    }


def main():
    print("=" * 75)
    print("Cross-Validation Backtest (Rolling fold + Reverse fold)")
    print("=" * 75)

    sector_panel = pd.read_parquet(SECTOR_PANEL)
    print(f"\nLoaded sector panel: {len(sector_panel):,} rows, {sector_panel['date'].min()} ~ {sector_panel['date'].max()}")

    feat_df, ret_pivot = build_features(sector_panel)
    print(f"Features: {len(feat_df)} days ({feat_df.index.min()} ~ {feat_df.index.max()})")

    # KOSPI
    with open(KOSPI_HISTORY, "r", encoding="utf-8") as f:
        kospi_dict = json.load(f)
    kospi_series = pd.Series(kospi_dict).astype(float).sort_index()
    kospi_series.index = pd.to_datetime(kospi_series.index).strftime("%Y-%m-%d")
    kospi_ret = kospi_series.pct_change().dropna()
    print(f"KOSPI: {len(kospi_ret)} days ({kospi_ret.index.min()} ~ {kospi_ret.index.max()})")

    fold_results = {}
    for name, ts, te, vs, ve in FOLDS:
        print(f"\n{'-' * 75}")
        print(f"[{name}]")

        # Train period
        train = feat_df.copy()
        if ts is not None:
            train = train[train.index >= ts]
        if te is not None:
            train = train[train.index <= te]
        # Test period
        test = feat_df.copy()
        if vs is not None:
            test = test[test.index >= vs]
        if ve is not None:
            test = test[test.index <= ve]

        if len(train) < 252 or len(test) < 60:
            print(f"  Skip: train={len(train)}, test={len(test)} (too short)")
            continue
        print(f"  Train: {train.index.min()} ~ {train.index.max()} ({len(train)} days)")
        print(f"  Test:  {test.index.min()} ~ {test.index.max()} ({len(test)} days)")

        # HMM fit
        t0 = time.time()
        X_train = train[FEAT_COLS].values
        model = fit_hmm(X_train)
        if model is None:
            print(f"  HMM fit 실패")
            continue
        print(f"  HMM fit ({time.time()-t0:.1f}s)")

        # Predict regimes
        X_test = test[FEAT_COLS].values
        regimes_train = model.predict(X_train)
        regimes_test = model.predict(X_test)
        train_dist = pd.Series(regimes_train).value_counts().to_dict()
        test_dist = pd.Series(regimes_test).value_counts().to_dict()
        print(f"  Train regimes: {train_dist}")
        print(f"  Test regimes:  {test_dist}")

        # Train winners (look-ahead 방지)
        ret_pivot_train = ret_pivot.loc[(ret_pivot.index >= train.index.min()) & (ret_pivot.index <= train.index.max())]
        winners = compute_train_winners(regimes_train, ret_pivot_train, train.index.tolist(), N_REGIMES)

        # KOSPI aligned to test dates
        test_dates_str = test.index.tolist()
        kospi_aligned = pd.Series([kospi_ret.get(d, np.nan) for d in test_dates_str], index=test_dates_str).fillna(0)

        # Backtest
        ret_pivot_test = ret_pivot.loc[(ret_pivot.index >= test.index.min()) & (ret_pivot.index <= test.index.max())]
        r = run_backtest(regimes_test, ret_pivot_test, test.index.tolist(), kospi_aligned, winners)
        if r:
            fold_results[name] = r
            print(f"  Strategy:   cum {r['cum_return']*100:+6.1f}%  ann {r['annualized_return']*100:+6.1f}%  Sharpe {r['sharpe']:+5.2f}  MDD {r['max_drawdown']*100:+6.1f}%  trades {r['n_trades']}")
            print(f"  Benchmark:  cum {r['benchmark_cum']*100:+6.1f}%  ann {r['benchmark_ann']*100:+6.1f}%  Sharpe {r['benchmark_sharpe']:+5.2f}")
            print(f"  Alpha: {r['alpha']*100:+6.1f}% /yr")

    # Summary
    print(f"\n{'=' * 75}")
    print("Summary")
    print('=' * 75)
    print(f"\n{'Fold':<28s} {'Strat ann':>10s} {'Bench ann':>10s} {'Alpha':>10s} {'Strat Sharpe':>14s} {'Trades':>8s}")
    for name, r in fold_results.items():
        print(f"{name:<28s} {r['annualized_return']*100:>+9.1f}% {r['benchmark_ann']*100:>+9.1f}% {r['alpha']*100:>+9.1f}% {r['sharpe']:>+14.2f} {r['n_trades']:>8d}")

    # Robustness 지표
    alphas = [r['alpha'] for r in fold_results.values()]
    sharpes = [r['sharpe'] for r in fold_results.values()]
    pos_alpha = sum(1 for a in alphas if a > 0)
    print(f"\nRobustness:")
    print(f"  Folds with positive alpha: {pos_alpha}/{len(alphas)}")
    print(f"  Mean alpha: {np.mean(alphas)*100:+.1f}%/yr")
    print(f"  Median alpha: {np.median(alphas)*100:+.1f}%/yr")
    print(f"  Mean Sharpe: {np.mean(sharpes):+.2f}")
    print(f"  Worst Sharpe: {min(sharpes):+.2f}")
    print(f"  Best Sharpe: {max(sharpes):+.2f}")

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"folds": fold_results, "params": {"top_n": TOP_N, "n_regimes": N_REGIMES, "tc": TC}},
                  f, ensure_ascii=False, indent=2, default=str)
    print(f"\nOK saved -> {OUT_JSON}")


if __name__ == "__main__":
    main()
