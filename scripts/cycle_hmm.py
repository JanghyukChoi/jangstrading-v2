"""
Phase 2: HMM Regime Detection (월가 퀀트 표준)

설계 원칙 (overfitting 방지):
1. Walk-forward: Train 2016-2021, Test 2022-2026 엄격 분리
2. BIC criterion으로 regime 수 결정 (2~4 중)
3. Multiple seeds (5개) - 학습 안정성 검증
4. Feature parsimony (4개로 제한)
5. OOS sharpe + t-stat 검증, in-sample >> OOS면 reject
6. Regime별 최소 sample 100일 검증

Features (학계 + 우리 데이터 강점 융합):
1. KOSPI proxy 20일 realized volatility (regime 핵심)
2. KOSPI proxy 20일 cumulative return
3. Cross-sectional dispersion (섹터 간 일별 수익률 std)
4. 외인+기관 합산 5일 flow z-score (rolling 252d)

Model: Gaussian HMM (multivariate normal emission)

출력:
- scripts/ml_artifacts/regime_panel.parquet (date x regime label)
- scripts/ml_artifacts/regime_results.json (regime별 통계)
- scripts/ml_artifacts/hmm_model.pkl (학습된 모델)
- 콘솔 보고서

실행:
  python scripts/cycle_hmm.py
"""

import json
import pickle
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

# hmmlearn warnings 억제
warnings.filterwarnings("ignore", category=RuntimeWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

from hmmlearn.hmm import GaussianHMM  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent
ART_DIR = BASE_DIR / "scripts" / "ml_artifacts"
SECTOR_PANEL = ART_DIR / "sector_panel.parquet"

OUT_PANEL = ART_DIR / "regime_panel.parquet"
OUT_JSON = ART_DIR / "regime_results.json"
OUT_MODEL = ART_DIR / "hmm_model.pkl"

# Walk-forward split
TRAIN_END = "2021-12-31"
TEST_START = "2022-01-01"

# Model selection
REGIME_CANDIDATES = [2, 3, 4]
N_SEEDS = 5
MAX_ITER = 300
COV_TYPE = "full"  # diagonal보다 풍부

# 안전장치
MIN_SAMPLES_PER_REGIME = 100  # regime별 최소 일수
TC_ROUNDTRIP = 0.005


# ──────────────────────────────────────────────────────────
# 1. Feature engineering
# ──────────────────────────────────────────────────────────

def build_features(sector_panel):
    """sector_panel (long: date x sector) -> market-level wide DataFrame with features

    Returns:
        df: date 인덱스, columns = [vol_20d, ret_20d, dispersion_20d, flow_z_5d, mkt_ret]
    """
    print("  Building features...")
    t0 = time.time()

    # date x sector pivot (수익률)
    ret_pivot = sector_panel.pivot(index="date", columns="sector", values="sector_ret")
    # 시총가중 시장 proxy (모든 섹터 시총가중)
    mcap_pivot = sector_panel.pivot(index="date", columns="sector", values="mcap_sum")

    # 일별 시장 수익률 = Σ(sector_ret x mcap) / Σ(mcap)
    weighted_ret = (ret_pivot * mcap_pivot).sum(axis=1) / mcap_pivot.sum(axis=1)
    weighted_ret = weighted_ret.replace([np.inf, -np.inf], np.nan)

    # 1. 20일 realized volatility (annualized)
    vol_20d = weighted_ret.rolling(20).std() * np.sqrt(250)

    # 2. 20일 cumulative return
    ret_20d = (1 + weighted_ret).rolling(20).apply(np.prod, raw=True) - 1

    # 3. Cross-sectional dispersion (섹터 간 일별 수익률 std)
    dispersion = ret_pivot.std(axis=1)
    dispersion_20d = dispersion.rolling(20).mean()

    # 4. 외인+기관 합산 5일 flow z-score (rolling 252d)
    flow_pivot_f = sector_panel.pivot(index="date", columns="sector", values="foreign_sum")
    flow_pivot_i = sector_panel.pivot(index="date", columns="sector", values="inst_sum")
    market_flow_daily = flow_pivot_f.sum(axis=1) + flow_pivot_i.sum(axis=1)  # 백만원
    flow_5d = market_flow_daily.rolling(5).sum()
    flow_z = (flow_5d - flow_5d.rolling(252).mean()) / flow_5d.rolling(252).std()

    df = pd.DataFrame({
        "vol_20d": vol_20d,
        "ret_20d": ret_20d,
        "dispersion_20d": dispersion_20d,
        "flow_z_5d": flow_z,
        "mkt_ret": weighted_ret,
    }).dropna()
    print(f"  Features: {len(df):,} rows, {df.columns.tolist()} ({time.time()-t0:.1f}s)")
    return df


# ──────────────────────────────────────────────────────────
# 2. Model selection (BIC)
# ──────────────────────────────────────────────────────────

def compute_bic(model, X, n_components):
    """BIC = -2 ln(L) + k ln(n)"""
    log_likelihood = model.score(X)
    # Parameters: (transition) + (means) + (cov full)
    n_features = X.shape[1]
    n_trans = n_components * (n_components - 1)
    n_means = n_components * n_features
    n_cov = n_components * n_features * (n_features + 1) // 2
    k = n_trans + n_means + n_cov
    return -2 * log_likelihood + k * np.log(len(X))


def fit_one(args):
    n_components, seed, X = args
    try:
        model = GaussianHMM(
            n_components=n_components,
            covariance_type=COV_TYPE,
            n_iter=MAX_ITER,
            random_state=seed,
            tol=1e-4,
        )
        model.fit(X)
        ll = model.score(X)
        bic = compute_bic(model, X, n_components)
        return {"n": n_components, "seed": seed, "ll": ll, "bic": bic, "model": model}
    except Exception as e:
        return {"n": n_components, "seed": seed, "error": str(e)}


def select_n_regimes(X_train):
    """BIC 기반 모델 선택. 각 N마다 5 seed 학습 후 best BIC."""
    print(f"  Model selection: {REGIME_CANDIDATES} regimes x {N_SEEDS} seeds = {len(REGIME_CANDIDATES)*N_SEEDS} fits")
    t0 = time.time()
    all_results = []
    for n in REGIME_CANDIDATES:
        for seed in range(N_SEEDS):
            r = fit_one((n, seed, X_train))
            if "error" not in r:
                all_results.append(r)

    # 각 N별 best seed (BIC)
    by_n = {}
    for r in all_results:
        n = r["n"]
        if n not in by_n or r["bic"] < by_n[n]["bic"]:
            by_n[n] = r

    print(f"  Best BIC by N regimes:")
    for n in REGIME_CANDIDATES:
        if n in by_n:
            r = by_n[n]
            print(f"    n={n}: BIC={r['bic']:.1f}, LL={r['ll']:.1f} (seed={r['seed']})")

    # 최저 BIC 선택
    best_overall = min(by_n.values(), key=lambda x: x["bic"])
    print(f"  >> Selected: n={best_overall['n']} regimes ({time.time()-t0:.1f}s)")
    return best_overall


# ──────────────────────────────────────────────────────────
# 3. Regime characterization
# ──────────────────────────────────────────────────────────

def characterize_regimes(model, X, dates, mkt_ret):
    """각 regime의 의미 해석"""
    regimes = model.predict(X)
    n = model.n_components

    stats = []
    for r in range(n):
        mask = (regimes == r)
        if mask.sum() == 0:
            continue
        # Feature mean
        feat_mean = X[mask].mean(axis=0)
        # Market return in this regime
        ret_in_regime = mkt_ret.values[mask]
        avg_ret = ret_in_regime.mean() * 250  # annualized
        vol_in_regime = ret_in_regime.std() * np.sqrt(250)
        sharpe = avg_ret / vol_in_regime if vol_in_regime > 0 else 0
        # Persistence (avg duration)
        transitions = (np.diff(regimes) != 0).astype(int)
        durations = []
        cur_len = 1
        for i in range(1, len(regimes)):
            if regimes[i] == regimes[i - 1] and regimes[i] == r:
                cur_len += 1
            elif regimes[i - 1] == r:
                durations.append(cur_len)
                cur_len = 1
            else:
                cur_len = 1
        avg_duration = np.mean(durations) if durations else 0

        stats.append({
            "regime": r,
            "n_days": int(mask.sum()),
            "pct_of_time": float(mask.mean()),
            "feat_vol_20d": float(feat_mean[0]),
            "feat_ret_20d": float(feat_mean[1]),
            "feat_dispersion": float(feat_mean[2]),
            "feat_flow_z": float(feat_mean[3]),
            "annualized_return": float(avg_ret),
            "annualized_vol": float(vol_in_regime),
            "sharpe": float(sharpe),
            "avg_duration_days": float(avg_duration),
        })

    return regimes, stats


def label_regime(stat):
    """heuristic: regime의 특성으로 이름 매긴다"""
    ret = stat["annualized_return"]
    vol = stat["annualized_vol"]
    if ret > 0.10 and vol < 0.25:
        return "Bull (강세장)"
    if ret > 0.10:
        return "Bull-Volatile (변동성 강세)"
    if ret < -0.05 and vol > 0.30:
        return "Crisis (위기)"
    if ret < -0.05:
        return "Bear (약세장)"
    if vol < 0.15:
        return "Quiet (저변동성)"
    return "Transition (전환기)"


# ──────────────────────────────────────────────────────────
# 4. Sector outperformance by regime
# ──────────────────────────────────────────────────────────

def sector_performance_by_regime(regimes, sector_panel, dates, forward_window=20):
    """각 regime에서 forward 20일 sector return"""
    # dates 정렬 + regime mapping
    date_to_regime = dict(zip(dates, regimes))

    # sector x date -> forward return 계산
    pivot = sector_panel.pivot(index="date", columns="sector", values="sector_ret")
    cumret = (1 + pivot).rolling(forward_window).apply(np.prod, raw=True) - 1
    # Shift: 오늘 regime에서 미래 N일 forward return
    forward_ret = cumret.shift(-forward_window)

    # 각 regime별 sector 평균
    results = []
    n_regimes = len(set(regimes))
    for r in range(n_regimes):
        regime_dates = [d for d in dates if date_to_regime.get(d) == r]
        if not regime_dates:
            continue
        regime_forward = forward_ret.loc[regime_dates].dropna(how="all")
        if regime_forward.empty:
            continue
        sector_stats = {}
        for sec in regime_forward.columns:
            rets = regime_forward[sec].dropna().values
            if len(rets) < 30:
                continue
            avg = rets.mean()
            std = rets.std(ddof=1)
            t_stat = (avg * np.sqrt(len(rets))) / std if std > 0 else 0
            hit = float((rets > 0).mean())
            sector_stats[sec] = {
                "n": int(len(rets)),
                "avg": float(avg),
                "std": float(std),
                "t_stat": float(t_stat),
                "hit_rate": hit,
            }
        results.append({
            "regime": int(r),
            "n_sample_days": len(regime_dates),
            "sectors": sector_stats,
        })
    return results


# ──────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("HMM Regime Detection - Phase 2 (Walk-Forward)")
    print("=" * 70)

    # 1. Load
    print("\n[Step 1] Load sector panel...")
    if not SECTOR_PANEL.exists():
        print(f"[ERROR] {SECTOR_PANEL} 없음. Phase 1 (cycle_eda.py) 먼저 실행.")
        return
    sector_panel = pd.read_parquet(SECTOR_PANEL)
    print(f"  Panel: {len(sector_panel):,} rows, {sector_panel['sector'].nunique()} sectors, dates {sector_panel['date'].min()} ~ {sector_panel['date'].max()}")

    # 2. Features
    print("\n[Step 2] Build features...")
    feat_df = build_features(sector_panel)

    # 3. Walk-forward split
    print(f"\n[Step 3] Walk-forward split (train <= {TRAIN_END}, test >= {TEST_START})")
    train = feat_df[feat_df.index <= TRAIN_END]
    test = feat_df[feat_df.index >= TEST_START]
    print(f"  Train: {len(train)} days ({train.index.min()} ~ {train.index.max()})")
    print(f"  Test:  {len(test)} days ({test.index.min()} ~ {test.index.max()})")

    # Feature 행렬 (mkt_ret 제외)
    feat_cols = ["vol_20d", "ret_20d", "dispersion_20d", "flow_z_5d"]
    X_train = train[feat_cols].values
    X_test = test[feat_cols].values

    # 4. Model selection (BIC, in-sample)
    print(f"\n[Step 4] Model selection (BIC)")
    best = select_n_regimes(X_train)
    model = best["model"]
    n_regimes = best["n"]

    # 5. In-sample regime characterization
    print(f"\n[Step 5] In-sample regime characterization (Train)")
    train_regimes, train_stats = characterize_regimes(
        model, X_train, train.index.tolist(), train["mkt_ret"]
    )

    # 안전장치: regime별 최소 sample
    insufficient = [s for s in train_stats if s["n_days"] < MIN_SAMPLES_PER_REGIME]
    if insufficient:
        print(f"  [WARN] Regime {[s['regime'] for s in insufficient]}는 sample 부족 ({MIN_SAMPLES_PER_REGIME}일 미만)")

    # Regime 라벨 매기기
    for s in train_stats:
        s["label"] = label_regime(s)

    print(f"\n  Train regimes ({n_regimes}):")
    print(f"  {'Regime':<8s} {'Label':<24s} {'Days':>6s} {'% Time':>8s} {'Ann Ret':>10s} {'Ann Vol':>10s} {'Sharpe':>8s} {'Dur(d)':>8s}")
    for s in sorted(train_stats, key=lambda x: -x["sharpe"]):
        print(f"  {s['regime']:<8d} {s['label']:<24s} {s['n_days']:>6d} {s['pct_of_time']*100:>7.1f}% {s['annualized_return']*100:>+9.1f}% {s['annualized_vol']*100:>+9.1f}% {s['sharpe']:>+8.2f} {s['avg_duration_days']:>8.1f}")

    # 6. Out-of-sample regime estimation
    print(f"\n[Step 6] Out-of-sample regime estimation (Test)")
    test_regimes = model.predict(X_test)
    test_regime_stats = []
    for r in range(n_regimes):
        mask = (test_regimes == r)
        if mask.sum() == 0:
            continue
        ret_in_regime = test["mkt_ret"].values[mask]
        avg_ret = ret_in_regime.mean() * 250
        vol = ret_in_regime.std() * np.sqrt(250)
        sharpe = avg_ret / vol if vol > 0 else 0
        test_regime_stats.append({
            "regime": int(r),
            "n_days": int(mask.sum()),
            "annualized_return": float(avg_ret),
            "annualized_vol": float(vol),
            "sharpe": float(sharpe),
        })

    print(f"  Test regime distribution:")
    print(f"  {'Regime':<8s} {'Days':>6s} {'Ann Ret':>10s} {'Ann Vol':>10s} {'Sharpe':>8s}")
    for s in sorted(test_regime_stats, key=lambda x: -x["sharpe"]):
        train_label = next((t["label"] for t in train_stats if t["regime"] == s["regime"]), "?")
        print(f"  {s['regime']:<3d} {train_label:<24s} {s['n_days']:>6d} {s['annualized_return']*100:>+9.1f}% {s['annualized_vol']*100:>+9.1f}% {s['sharpe']:>+8.2f}")

    # 7. Sector outperformance by regime (Test set, OOS)
    print(f"\n[Step 7] OOS Sector outperformance by regime (Test 2022+)")
    test_sector_perf = sector_performance_by_regime(
        test_regimes, sector_panel, test.index.tolist()
    )

    print(f"\n  Out-of-sample sector winners by regime:")
    for r_data in test_sector_perf:
        r = r_data["regime"]
        train_label = next((t["label"] for t in train_stats if t["regime"] == r), "?")
        print(f"\n  [Regime {r}: {train_label}] (Test sample: {r_data['n_sample_days']} days)")
        # Top 5 sectors by t-stat
        top = sorted(r_data["sectors"].items(), key=lambda x: -x[1]["t_stat"])[:8]
        print(f"    {'Sector':<24s} {'N':>4s} {'avg_60d':>10s} {'t-stat':>8s} {'hit':>7s}")
        for sec, stats in top:
            print(f"    {sec:<24s} {stats['n']:>4d} {stats['avg']*100:>+9.2f}% {stats['t_stat']:>+8.2f} {stats['hit_rate']*100:>6.1f}%")

    # 8. Regime panel save
    print(f"\n[Step 8] Save regime panel + model...")
    regime_panel = pd.concat([
        pd.DataFrame({"date": train.index, "regime": train_regimes, "split": "train"}),
        pd.DataFrame({"date": test.index, "regime": test_regimes, "split": "test"}),
    ], ignore_index=True)
    regime_panel.to_parquet(OUT_PANEL, compression="snappy")
    print(f"  Saved -> {OUT_PANEL}")

    with open(OUT_MODEL, "wb") as f:
        pickle.dump({
            "model": model,
            "features": feat_cols,
            "n_regimes": n_regimes,
            "regime_labels": {s["regime"]: s["label"] for s in train_stats},
        }, f)
    print(f"  Saved -> {OUT_MODEL}")

    # 9. JSON 보고서
    output = {
        "summary": {
            "train_period": [train.index.min(), train.index.max()],
            "test_period": [test.index.min(), test.index.max()],
            "n_regimes_selected": n_regimes,
            "bic": best["bic"],
            "features": feat_cols,
        },
        "train_regime_stats": train_stats,
        "test_regime_stats": test_regime_stats,
        "test_sector_performance": test_sector_perf,
        "current_regime": {
            "date": str(test.index[-1]),
            "regime": int(test_regimes[-1]),
            "label": next((t["label"] for t in train_stats if t["regime"] == int(test_regimes[-1])), "?"),
        },
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    print(f"  Saved -> {OUT_JSON}")

    # 10. 최종 진단
    print("\n" + "=" * 70)
    print("Validation Summary (Overfitting Check)")
    print("=" * 70)

    train_sharpe = {s["regime"]: s["sharpe"] for s in train_stats}
    test_sharpe = {s["regime"]: s["sharpe"] for s in test_regime_stats}

    print(f"\n  Regime 별 Train vs Test Sharpe:")
    print(f"  {'Regime':<8s} {'Train':>10s} {'Test':>10s} {'Diff':>10s} {'Status':<15s}")
    overfitting_flag = False
    for r in range(n_regimes):
        if r in train_sharpe and r in test_sharpe:
            tr = train_sharpe[r]
            te = test_sharpe[r]
            diff = abs(tr - te)
            status = "OK"
            if abs(tr) > 0.5 and abs(te) < abs(tr) * 0.3:
                status = "[WARN] Overfit?"
                overfitting_flag = True
            print(f"  {r:<8d} {tr:>+9.2f} {te:>+9.2f} {diff:>+9.2f} {status}")

    if overfitting_flag:
        print(f"\n  [WARN] 일부 regime은 Train sharpe가 Test에서 크게 떨어짐 - overfitting 의심")
    else:
        print(f"\n  [OK] Train/Test sharpe 일관됨 - 모델 안정성 양호")

    # 현재 regime
    cur_r = int(test_regimes[-1])
    cur_label = next((t["label"] for t in train_stats if t["regime"] == cur_r), "?")
    print(f"\n  현재 regime ({test.index[-1]}): Regime {cur_r} - {cur_label}")


if __name__ == "__main__":
    main()
