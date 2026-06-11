"""
Phase 3: Regime-based Sector Rotation Strategy 백테스트

전략 정의 (월가 표준 정합):
- Train period (2017-2021): regime별 우세 섹터 결정 (forward 20d sector return 상위)
- Test period (2022-2026): 매일 시뮬레이션 (look-ahead bias 0)

매일:
  1. HMM으로 그 시점 regime 추론 (cycle_hmm.py 학습 모델)
  2. Regime 변화 발생 시 → 청산 + 새 regime의 top-N 섹터 동일가중 매수
  3. Hold 종료 조건에 따라 청산
  4. TC 0.5% (round-trip) 차감

3가지 strategy:
  A. Hold 20d after entry
  B. Hold 60d after entry
  C. Hold until regime change

Top-N 비교: 3, 5

벤치마크: KOSPI proxy (시총가중 시장 수익률)

지표:
  - 누적 수익률
  - 연환산 수익률
  - Annual Sharpe
  - Max Drawdown
  - Hit rate (월별 vs 벤치마크)
  - 거래 횟수 (TC 영향)

실행:
  python scripts/backtest_regime_strategy.py
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

BASE_DIR = Path(__file__).resolve().parent.parent
ART_DIR = BASE_DIR / "scripts" / "ml_artifacts"
MODEL_DIR = BASE_DIR / "scripts" / "ml_models"
SECTOR_PANEL = ART_DIR / "sector_panel.parquet"
MODEL_PATH = MODEL_DIR / "hmm_model.pkl"
KOSPI_HISTORY = BASE_DIR / "public" / "data" / "kospi-history.json"
OUT_JSON = ART_DIR / "backtest_strategy_results.json"

TRAIN_END = "2021-12-31"
TEST_START = "2022-01-01"
TC = 0.005  # round-trip 0.5%

# Strategy 정의
HOLDING_OPTIONS = ["20d", "60d", "regime_change", "20d_or_regime", "60d_or_regime"]
TOP_N_OPTIONS = [3, 5]
STAY_INVESTED_OPTIONS = [False, True]  # cash drag 비교

# Bootstrap
BOOTSTRAP_N = 1000
BLOCK_SIZE = 60  # 영업일 (regime 평균 지속과 비슷)


# ──────────────────────────────────────────────────────────
# 1. Data loading
# ──────────────────────────────────────────────────────────

def load_data():
    print("[Step 1] Loading...")
    sector_panel = pd.read_parquet(SECTOR_PANEL)
    with open(MODEL_PATH, "rb") as f:
        saved = pickle.load(f)
    model = saved["model"]
    feat_cols = saved["features"]
    print(f"  Sector panel: {len(sector_panel):,} rows")
    print(f"  Model: {saved['n_regimes']} regimes")
    return sector_panel, model, feat_cols, saved["n_regimes"]


# ──────────────────────────────────────────────────────────
# 2. Feature engineering (cycle_hmm.py와 동일)
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


# ──────────────────────────────────────────────────────────
# 3. Train 시기 regime별 우세 섹터 (look-ahead 방지)
# ──────────────────────────────────────────────────────────

def compute_train_winners(regimes_train, ret_pivot_train, dates_train, n_regimes, forward_window=20):
    """Train 데이터의 각 regime에서 forward 20d sector return 평균 top-N"""
    winners = {}
    cumret = (1 + ret_pivot_train).rolling(forward_window).apply(np.prod, raw=True) - 1
    forward = cumret.shift(-forward_window)
    for r in range(n_regimes):
        regime_dates = [d for d, rg in zip(dates_train, regimes_train) if rg == r]
        if not regime_dates:
            continue
        regime_forward = forward.loc[regime_dates].dropna(how="all")
        if regime_forward.empty:
            continue
        # 각 섹터 mean forward return
        means = regime_forward.mean()
        # 양수 mean만 + 상위 정렬
        positives = means[means > 0].sort_values(ascending=False)
        winners[r] = positives.index.tolist()  # 모든 양수 sector
    return winners


# ──────────────────────────────────────────────────────────
# 4. Backtest engine
# ──────────────────────────────────────────────────────────

def run_backtest(regimes_test, ret_pivot_test, dates_test, mkt_ret_test, train_winners, top_n, holding, stay_invested=False, tc=TC):
    """Test 시기 매일 시뮬레이션
    stay_invested: True면 청산 시 즉시 재매수 (cash drag 0)
       - 20d/60d 종료 시 같은 regime이면 같은 sector 재매수 (TC 0)
       - regime change 시 새 sector swap (TC 적용)
    Returns: dict with daily portfolio value + stats
    """
    cash = 1.0
    positions = []
    n_trades = 0
    pv_log = []
    prev_regime = -1

    for i, date in enumerate(dates_test):
        cur_regime = regimes_test[i]

        # 1) Update positions with daily return
        for pos in positions:
            sec_ret = ret_pivot_test.loc[date, pos["sector"]] if pos["sector"] in ret_pivot_test.columns else 0
            if pd.isna(sec_ret):
                sec_ret = 0
            pos["weight"] *= (1 + sec_ret)

        # 2) Check exits
        regime_changed = (cur_regime != prev_regime) and i > 0
        new_positions = []
        exited_value = 0.0
        for pos in positions:
            held_days = i - pos["entry_idx"]
            should_exit = False
            if holding == "20d" and held_days >= 20:
                should_exit = True
            elif holding == "60d" and held_days >= 60:
                should_exit = True
            elif holding == "regime_change" and regime_changed:
                should_exit = True
            elif holding == "20d_or_regime" and (held_days >= 20 or regime_changed):
                should_exit = True
            elif holding == "60d_or_regime" and (held_days >= 60 or regime_changed):
                should_exit = True
            if should_exit:
                if stay_invested and not regime_changed:
                    # 같은 regime: 그대로 hold (TC 0, entry_idx만 갱신 = 시간 hold 리셋)
                    pos["entry_idx"] = i
                    new_positions.append(pos)
                else:
                    exited_value += pos["weight"] * (1 - tc / 2)
                    n_trades += 1
            else:
                new_positions.append(pos)
        cash += exited_value
        positions = new_positions

        # 3) Check entry
        if not positions:
            # 모든 hold 종료 + entry 가능
            # Default: regime change 시점에만 매수
            # Stay-invested: 매일 cash 있으면 즉시 매수
            should_enter = (i == 0 or regime_changed) or (stay_invested and cash > 0)
            if should_enter:
                top_sectors = train_winners.get(cur_regime, [])[:top_n]
                if top_sectors and cash > 0:
                    entry_weight = (cash * (1 - tc / 2)) / len(top_sectors)
                    for sec in top_sectors:
                        positions.append({
                            "sector": sec,
                            "entry_idx": i,
                            "entry_regime": cur_regime,
                            "weight": entry_weight,
                        })
                    cash = 0
                    n_trades += len(top_sectors)

        # 4) Portfolio value
        pv = cash + sum(p["weight"] for p in positions)
        pv_log.append({"date": str(date), "pv": pv})
        prev_regime = cur_regime

    # Force close at end
    for pos in positions:
        cash += pos["weight"] * (1 - tc / 2)

    # Daily returns
    pv_series = pd.DataFrame(pv_log).set_index("date")["pv"]
    daily_ret = pv_series.pct_change().dropna()

    # Benchmark = mkt_ret_test (외부에서 KOSPI 일별 수익률 주입)
    bench_ret = mkt_ret_test.copy()

    # Stats
    n_days = len(daily_ret)
    cum_ret = pv_series.iloc[-1] - 1
    ann_ret = (1 + cum_ret) ** (250 / n_days) - 1 if n_days > 0 else 0
    ann_vol = daily_ret.std() * np.sqrt(250) if len(daily_ret) > 1 else 0
    sharpe = ann_ret / ann_vol if ann_vol > 0 else 0

    # MDD
    cum_pv = pv_series.values
    running_max = np.maximum.accumulate(cum_pv)
    drawdown = (cum_pv - running_max) / running_max
    mdd = drawdown.min()

    # Monthly hit rate vs benchmark
    pv_series.index = pd.to_datetime(pv_series.index)
    monthly_pv = pv_series.resample("M").last()
    monthly_strat_ret = monthly_pv.pct_change().dropna()
    bench_series = (1 + bench_ret).cumprod()
    bench_series.index = pd.to_datetime(bench_series.index)
    monthly_bench = bench_series.resample("M").last()
    monthly_bench_ret = monthly_bench.pct_change().dropna()
    aligned = pd.concat([monthly_strat_ret, monthly_bench_ret], axis=1).dropna()
    aligned.columns = ["strat", "bench"]
    monthly_win_rate = (aligned["strat"] > aligned["bench"]).mean() if len(aligned) > 0 else 0

    # Benchmark cumulative
    bench_cum = (1 + bench_ret).cumprod().iloc[-1] - 1
    bench_ann_vol = bench_ret.std() * np.sqrt(250)
    bench_ann_ret = (1 + bench_cum) ** (250 / len(bench_ret)) - 1
    bench_sharpe = bench_ann_ret / bench_ann_vol if bench_ann_vol > 0 else 0

    return {
        "n_days": n_days,
        "cum_return": float(cum_ret),
        "annualized_return": float(ann_ret),
        "annualized_vol": float(ann_vol),
        "sharpe": float(sharpe),
        "max_drawdown": float(mdd),
        "n_trades": int(n_trades),
        "monthly_win_rate_vs_bench": float(monthly_win_rate),
        "benchmark_cum_return": float(bench_cum),
        "benchmark_ann_return": float(bench_ann_ret),
        "benchmark_sharpe": float(bench_sharpe),
        "alpha": float(ann_ret - bench_ann_ret),
        "daily_returns": daily_ret.tolist(),  # bootstrap용
    }


# ──────────────────────────────────────────────────────────
# Bootstrap (C: confidence intervals)
# ──────────────────────────────────────────────────────────

def block_bootstrap(daily_returns, n_iter=BOOTSTRAP_N, block_size=BLOCK_SIZE, seed=42):
    """Block bootstrap. 일별 수익률을 block 단위로 재샘플링.
    Returns: dict with median + 5%/95% CI of (cum_return, annualized_return, sharpe, max_dd)
    """
    if len(daily_returns) < block_size * 2:
        return None
    np.random.seed(seed)
    arr = np.asarray(daily_returns, dtype=np.float64)
    n = len(arr)
    n_blocks = int(np.ceil(n / block_size))

    cums, anns, sharpes, mdds = [], [], [], []
    for _ in range(n_iter):
        # 무작위 시작점으로 block 뽑아 연결
        starts = np.random.randint(0, n - block_size + 1, size=n_blocks)
        blocks = [arr[s:s + block_size] for s in starts]
        sample = np.concatenate(blocks)[:n]
        # Stats
        cum = float(np.prod(1 + sample) - 1)
        ann_ret = (1 + cum) ** (250 / n) - 1
        std = sample.std(ddof=1)
        sharpe = (ann_ret / (std * np.sqrt(250))) if std > 0 else 0
        # MDD
        cum_pv = np.cumprod(1 + sample)
        running_max = np.maximum.accumulate(cum_pv)
        mdd = float(((cum_pv - running_max) / running_max).min())
        cums.append(cum)
        anns.append(ann_ret)
        sharpes.append(sharpe)
        mdds.append(mdd)

    def stat(arr):
        a = np.asarray(arr)
        return {
            "median": float(np.median(a)),
            "p05": float(np.percentile(a, 5)),
            "p95": float(np.percentile(a, 95)),
            "p25": float(np.percentile(a, 25)),
            "p75": float(np.percentile(a, 75)),
        }

    return {
        "cum_return": stat(cums),
        "annualized_return": stat(anns),
        "sharpe": stat(sharpes),
        "max_drawdown": stat(mdds),
        "n_iter": n_iter,
        "block_size": block_size,
    }


# ──────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("Regime Strategy Backtest (Walk-Forward)")
    print("=" * 70)

    sector_panel, model, feat_cols, n_regimes = load_data()

    print("\n[Step 2] Building features...")
    feat_df, ret_pivot = build_features(sector_panel)
    train = feat_df[feat_df.index <= TRAIN_END]
    test = feat_df[feat_df.index >= TEST_START]
    print(f"  Train: {len(train)} days ({train.index.min()} ~ {train.index.max()})")
    print(f"  Test:  {len(test)} days ({test.index.min()} ~ {test.index.max()})")

    # Predict regimes
    print("\n[Step 3] HMM regime prediction...")
    X_train = train[feat_cols].values
    X_test = test[feat_cols].values
    regimes_train = model.predict(X_train)
    regimes_test = model.predict(X_test)
    print(f"  Train regime distribution: {pd.Series(regimes_train).value_counts().to_dict()}")
    print(f"  Test regime distribution:  {pd.Series(regimes_test).value_counts().to_dict()}")

    # Train sector winners (look-ahead 방지)
    print("\n[Step 4] Computing Train regime->sector winners (no look-ahead)...")
    ret_pivot_train = ret_pivot.loc[ret_pivot.index <= TRAIN_END]
    train_winners = compute_train_winners(
        regimes_train, ret_pivot_train, train.index.tolist(), n_regimes
    )
    for r in range(n_regimes):
        top5 = train_winners.get(r, [])[:5]
        print(f"  Regime {r}: top-5 = {top5}")

    # Load real KOSPI for benchmark
    print("\n[Step 4b] Loading KOSPI history for fair benchmark...")
    with open(KOSPI_HISTORY, "r", encoding="utf-8") as f:
        kospi_dict = json.load(f)
    kospi_series = pd.Series(kospi_dict).astype(float).sort_index()
    kospi_series.index = pd.to_datetime(kospi_series.index).strftime("%Y-%m-%d")
    kospi_ret = kospi_series.pct_change().dropna()
    kospi_ret_test = kospi_ret[(kospi_ret.index >= TEST_START)]
    print(f"  KOSPI test ret: {len(kospi_ret_test)} days, range {kospi_ret_test.index.min()} ~ {kospi_ret_test.index.max()}")

    # Backtest matrix
    print("\n[Step 5] Backtesting strategies...")
    ret_pivot_test = ret_pivot.loc[ret_pivot.index >= TEST_START]

    # Test 인덱스에 맞춰 KOSPI 정렬
    test_dates_str = test.index.tolist()
    kospi_aligned = pd.Series([kospi_ret.get(d, np.nan) for d in test_dates_str], index=test_dates_str)
    # 첫 NaN은 0으로 (계산 출발점)
    kospi_aligned = kospi_aligned.fillna(0)
    print(f"  Using real KOSPI as benchmark ({(kospi_aligned != 0).sum()} matched days)")

    results = {}
    for top_n in TOP_N_OPTIONS:
        for holding in HOLDING_OPTIONS:
            for stay in STAY_INVESTED_OPTIONS:
                suffix = "_stay" if stay else ""
                key = f"top{top_n}_{holding}{suffix}"
                t0 = time.time()
                r = run_backtest(
                    regimes_test, ret_pivot_test, test.index.tolist(),
                    kospi_aligned, train_winners, top_n, holding, stay_invested=stay
                )
                r["params"] = {"top_n": top_n, "holding": holding, "stay_invested": stay}
                results[key] = r
                print(f"  [{key:<30s}] cum={r['cum_return']*100:+6.1f}% ann={r['annualized_return']*100:+6.1f}% sharpe={r['sharpe']:+5.2f} MDD={r['max_drawdown']*100:+6.1f}% trades={r['n_trades']:>4d} ({time.time()-t0:.1f}s)")

    # Report
    print("\n" + "=" * 70)
    print("Backtest Summary (OOS Test 2022-2026)")
    print("=" * 70)
    print(f"\n{'Strategy':<25s} {'Cum':>8s} {'Ann':>8s} {'Sharpe':>8s} {'MDD':>8s} {'Win%':>7s} {'Trades':>8s} {'Alpha':>8s}")
    bench_cum = list(results.values())[0]["benchmark_cum_return"]
    bench_ann = list(results.values())[0]["benchmark_ann_return"]
    bench_sharpe = list(results.values())[0]["benchmark_sharpe"]
    print(f"{'(Benchmark: KOSPI proxy)':<25s} {bench_cum*100:>+7.1f}% {bench_ann*100:>+7.1f}% {bench_sharpe:>+8.2f} {'-':>8s} {'-':>7s} {'0':>8s} {'-':>8s}")
    print()
    for key, r in sorted(results.items(), key=lambda x: -x[1]["sharpe"]):
        print(f"{key:<25s} {r['cum_return']*100:>+7.1f}% {r['annualized_return']*100:>+7.1f}% {r['sharpe']:>+8.2f} {r['max_drawdown']*100:>+7.1f}% {r['monthly_win_rate_vs_bench']*100:>6.1f}% {r['n_trades']:>8d} {r['alpha']*100:>+7.1f}%")

    # Best strategy (real alpha, n_trades >= 10 — 충분한 거래)
    print()
    real_strategies = {k: v for k, v in results.items() if v["n_trades"] >= 10}
    if real_strategies:
        best_real = max(real_strategies.items(), key=lambda x: x[1]["sharpe"])
        print(f"[Best real-strategy (trades>=10) by Sharpe]: {best_real[0]} - Sharpe {best_real[1]['sharpe']:.2f}, Alpha {best_real[1]['alpha']*100:+.1f}%/yr, trades {best_real[1]['n_trades']}")

    # Bootstrap (Top 5 strategies)
    print(f"\n[Step 6] Block bootstrap ({BOOTSTRAP_N} iter, block={BLOCK_SIZE}d) for top-5 by Sharpe...")
    top5_by_sharpe = sorted(results.items(), key=lambda x: -x[1]["sharpe"])[:5]
    bootstrap_results = {}
    for key, r in top5_by_sharpe:
        t0 = time.time()
        boot = block_bootstrap(r["daily_returns"])
        bootstrap_results[key] = boot
        if boot:
            print(f"  [{key}] Sharpe median {boot['sharpe']['median']:.2f} [5%-95% CI: {boot['sharpe']['p05']:.2f} ~ {boot['sharpe']['p95']:.2f}], ann_ret median {boot['annualized_return']['median']*100:+.1f}% [{boot['annualized_return']['p05']*100:+.1f}% ~ {boot['annualized_return']['p95']*100:+.1f}%] ({time.time()-t0:.1f}s)")

    # 결과 정리 (daily_returns 제거 - 너무 큼)
    results_clean = {k: {kk: vv for kk, vv in v.items() if kk != "daily_returns"} for k, v in results.items()}

    # Save
    out = {
        "params": {
            "train_end": TRAIN_END,
            "test_start": TEST_START,
            "tc_roundtrip": TC,
            "top_n_options": TOP_N_OPTIONS,
            "holding_options": HOLDING_OPTIONS,
            "bootstrap_n": BOOTSTRAP_N,
            "block_size": BLOCK_SIZE,
        },
        "n_regimes": n_regimes,
        "train_winners_top5": {str(r): train_winners.get(r, [])[:5] for r in range(n_regimes)},
        "results": results_clean,
        "bootstrap": bootstrap_results,
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print(f"\nOK saved -> {OUT_JSON}")


if __name__ == "__main__":
    main()
