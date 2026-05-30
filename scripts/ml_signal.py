"""
AI 판별 수급 주도주 - ML (LightGBM) 기반 60일 보유 시그널

학계 근거:
- Gu, Kelly, Xiu (2020) "Empirical Asset Pricing via Machine Learning" - Tree models 안정
- AQR research - simple ML factor 합성
- Jegadeesh-Titman 12-1 momentum + 학계 검증 features

전체 흐름:
  1. 종목별 features 병렬 추출 (multiprocessing, 16코어)
  2. Train (2016-2021) / Val (2022) / Test (2023+) split
  3. LightGBM 학습 (max_depth 3, L2, early stopping)
  4. Test 백테스트 (probability >= threshold → 시그널, 60일 forward)
  5. 모델 저장 → 라이브 inference

실행:
  python scripts/ml_signal.py             # 전체 flow (feature → train → backtest)
  python scripts/ml_signal.py --features  # 특징만 빌드
  python scripts/ml_signal.py --train     # 학습만
  python scripts/ml_signal.py --backtest  # 백테스트만
  python scripts/ml_signal.py --infer     # 라이브 inference (오늘 날짜)
"""

import argparse
import json
import multiprocessing as mp
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
TS_DIR_BT = BASE_DIR / "scripts" / "backtest_data" / "timeseries"
TS_DIR_LIVE = BASE_DIR / "public" / "data" / "timeseries"
ART_DIR = BASE_DIR / "scripts" / "ml_artifacts"
ART_DIR.mkdir(parents=True, exist_ok=True)

FEATURES_PATH = ART_DIR / "features.parquet"
MODEL_PATH = ART_DIR / "lgbm_model.pkl"

FORWARD = 60
MIN_MCAP = 30_000_000_000  # 시총 300억 이상만 (noise filter)
TRAIN_END = "2021-12-31"
VAL_END = "2022-12-31"

# ───────────────────────────────────────────────────────────
# Feature extraction (per-ticker, vectorized)
# ───────────────────────────────────────────────────────────

def rolling_sum(arr, window):
    """numpy rolling sum (NaN-padded for first window-1)"""
    arr = np.asarray(arr, dtype=np.float64)
    cs = np.concatenate(([0.0], np.cumsum(arr)))
    res = np.full(len(arr), np.nan)
    res[window - 1:] = cs[window:] - cs[:-window]
    return res


def rolling_pos_ratio(arr, window):
    arr = np.asarray(arr, dtype=np.float64)
    pos = (arr > 0).astype(np.float64)
    cs = np.concatenate(([0.0], np.cumsum(pos)))
    res = np.full(len(arr), np.nan)
    res[window - 1:] = (cs[window:] - cs[:-window]) / window
    return res


def rolling_std(arr, window):
    """daily return std over rolling window"""
    arr = np.asarray(arr, dtype=np.float64)
    rets = np.full(len(arr), np.nan)
    valid = arr > 0
    for i in range(1, len(arr)):
        if valid[i] and valid[i - 1]:
            rets[i] = arr[i] / arr[i - 1] - 1
    # rolling std
    res = np.full(len(arr), np.nan)
    for i in range(window, len(arr)):
        win = rets[i - window:i]
        m = ~np.isnan(win)
        if m.sum() >= window // 2:
            res[i] = np.std(win[m])
    return res


def rolling_max(arr, window):
    """최근 window 내 최대값"""
    arr = np.asarray(arr, dtype=np.float64)
    res = np.full(len(arr), np.nan)
    for i in range(window - 1, len(arr)):
        win = arr[i - window + 1:i + 1]
        m = win > 0
        if m.any():
            res[i] = np.max(win[m])
    return res


def extract_features_one(args):
    """한 종목의 모든 영업일 features 추출."""
    ticker, data = args
    dates = data.get("dates", [])
    if len(dates) < 260:
        return None
    foreign = np.asarray(data.get("foreign", []), dtype=np.float64)
    inst = np.asarray(data.get("inst", []), dtype=np.float64)
    pension = np.asarray(data.get("pension", []), dtype=np.float64)
    prices = np.asarray(data.get("prices", []), dtype=np.float64)
    mcap = np.asarray(data.get("market_cap", []), dtype=np.float64)
    tv = np.asarray(data.get("trade_value", []), dtype=np.float64)
    n = len(dates)
    if len(foreign) != n or len(prices) != n or len(mcap) != n:
        return None

    # 가격 momentum (수익률)
    def mom(window, skip=0):
        out = np.full(n, np.nan)
        for i in range(window + skip, n):
            p_now = prices[i - skip]
            p_past = prices[i - window]
            if p_now > 0 and p_past > 0:
                out[i] = p_now / p_past - 1
        return out

    mom_20 = mom(20)
    mom_60 = mom(60)
    mom_120 = mom(120)
    mom_252_20 = mom(252, skip=20)  # 12-1 Jegadeesh-Titman

    # 변동성
    vol_20 = rolling_std(prices, 20)
    vol_60 = rolling_std(prices, 60)

    # 수급 누적 (백만원 단위)
    pen_5 = rolling_sum(pension, 5)
    pen_20 = rolling_sum(pension, 20)
    pen_60 = rolling_sum(pension, 60)
    for_5 = rolling_sum(foreign, 5)
    for_20 = rolling_sum(foreign, 20)
    for_60 = rolling_sum(foreign, 60)
    inst_5 = rolling_sum(inst, 5)
    inst_20 = rolling_sum(inst, 20)
    inst_60 = rolling_sum(inst, 60)

    # 시총 (원) → bps 변환: flow_백만원 * 1e10 / mcap_원
    safe_mcap = np.where(mcap > 0, mcap, np.nan)
    BP = 1e10
    pen_5_bps = pen_5 * BP / safe_mcap
    pen_20_bps = pen_20 * BP / safe_mcap
    pen_60_bps = pen_60 * BP / safe_mcap
    for_5_bps = for_5 * BP / safe_mcap
    for_20_bps = for_20 * BP / safe_mcap
    for_60_bps = for_60 * BP / safe_mcap
    inst_5_bps = inst_5 * BP / safe_mcap
    inst_20_bps = inst_20 * BP / safe_mcap
    inst_60_bps = inst_60 * BP / safe_mcap

    # 연기금 60일 양수일수 비율
    pen_pos_60 = rolling_pos_ratio(pension, 60)

    # 거래량 surge (20일 평균 대비)
    tv_avg_20 = rolling_sum(tv, 20) / 20
    surge_20 = np.where(tv_avg_20 > 0, tv / tv_avg_20 - 1, np.nan)

    # log 시총
    log_mcap = np.where(safe_mcap > 0, np.log(safe_mcap), np.nan)

    # 가격 위치
    price_ma60 = rolling_sum(prices, 60) / 60
    price_vs_ma60 = np.where(price_ma60 > 0, prices / price_ma60 - 1, np.nan)
    high_252 = rolling_max(prices, 252)
    price_vs_high = np.where(high_252 > 0, prices / high_252 - 1, np.nan)

    # 60일 forward return (label)
    fwd_ret = np.full(n, np.nan)
    fwd_idx = np.arange(n) + FORWARD
    valid = (fwd_idx < n)
    for i in np.where(valid)[0]:
        fi = fwd_idx[i]
        if prices[i] > 0 and prices[fi] > 0:
            fwd_ret[i] = prices[fi] / prices[i] - 1

    # DataFrame 구성 (시총 필터)
    mask = (mcap >= MIN_MCAP) & (~np.isnan(mom_252_20)) & (~np.isnan(pen_60_bps))
    if mask.sum() == 0:
        return None

    df = pd.DataFrame({
        "date": np.asarray(dates)[mask],
        "ticker": ticker,
        "mom_20": mom_20[mask],
        "mom_60": mom_60[mask],
        "mom_120": mom_120[mask],
        "mom_252_20": mom_252_20[mask],
        "vol_20": vol_20[mask],
        "vol_60": vol_60[mask],
        "pen_5_bps": pen_5_bps[mask],
        "pen_20_bps": pen_20_bps[mask],
        "pen_60_bps": pen_60_bps[mask],
        "pen_pos_60": pen_pos_60[mask],
        "for_5_bps": for_5_bps[mask],
        "for_20_bps": for_20_bps[mask],
        "for_60_bps": for_60_bps[mask],
        "inst_5_bps": inst_5_bps[mask],
        "inst_20_bps": inst_20_bps[mask],
        "inst_60_bps": inst_60_bps[mask],
        "surge_20": surge_20[mask],
        "log_mcap": log_mcap[mask],
        "price_vs_ma60": price_vs_ma60[mask],
        "price_vs_high": price_vs_high[mask],
        "fwd_ret": fwd_ret[mask],
    })
    return df


def load_ticker_data(ts_dir):
    """timeseries JSON 로드 (단일 thread, 빠름)"""
    files = [f for f in ts_dir.glob("*.json") if f.stem != "_index"]
    print(f"  Loading {len(files)} timeseries from {ts_dir}...")
    t0 = time.time()
    data = {}
    for f in files:
        try:
            d = json.load(open(f, "r", encoding="utf-8"))
            t = d.get("ticker") or f.stem
            data[t] = d
        except Exception:
            continue
    print(f"  Loaded {len(data)} in {time.time() - t0:.1f}s")
    return data


def build_features(ts_dir=TS_DIR_BT, save=True):
    """병렬 feature extraction"""
    ts = load_ticker_data(ts_dir)
    print(f"  Extracting features in parallel (workers={mp.cpu_count()})...")
    t0 = time.time()
    args = [(t, d) for t, d in ts.items()]
    with mp.Pool(processes=mp.cpu_count()) as pool:
        results = pool.map(extract_features_one, args, chunksize=20)
    dfs = [r for r in results if r is not None]
    df = pd.concat(dfs, ignore_index=True)
    elapsed = time.time() - t0
    print(f"  {len(df):,} rows in {elapsed:.1f}s")

    if save:
        df.to_parquet(FEATURES_PATH, compression="snappy")
        print(f"  Saved -> {FEATURES_PATH}")
    return df


# ───────────────────────────────────────────────────────────
# Train LightGBM
# ───────────────────────────────────────────────────────────

FEATURE_COLS = [
    "mom_20", "mom_60", "mom_120", "mom_252_20",
    "vol_20", "vol_60",
    "pen_5_bps", "pen_20_bps", "pen_60_bps", "pen_pos_60",
    "for_5_bps", "for_20_bps", "for_60_bps",
    "inst_5_bps", "inst_20_bps", "inst_60_bps",
    "surge_20", "log_mcap", "price_vs_ma60", "price_vs_high",
]


def train_model(df=None):
    import lightgbm as lgb

    if df is None:
        df = pd.read_parquet(FEATURES_PATH)
    df = df.dropna(subset=["fwd_ret"])
    # 라벨: 60일 후 양수 수익 (TC 차감 고려, 0.5% 이상 수익 = 1)
    df["label"] = (df["fwd_ret"] > 0.005).astype(int)

    train_df = df[df["date"] <= TRAIN_END]
    val_df = df[(df["date"] > TRAIN_END) & (df["date"] <= VAL_END)]
    test_df = df[df["date"] > VAL_END]

    print(f"\nTrain: {len(train_df):,} rows ({train_df['date'].min()} ~ {train_df['date'].max()})")
    print(f"Val  : {len(val_df):,} rows ({val_df['date'].min()} ~ {val_df['date'].max()})")
    print(f"Test : {len(test_df):,} rows ({test_df['date'].min()} ~ {test_df['date'].max()})")
    print(f"Train base rate (label=1): {train_df['label'].mean():.3f}")

    X_train = train_df[FEATURE_COLS].values
    y_train = train_df["label"].values
    X_val = val_df[FEATURE_COLS].values
    y_val = val_df["label"].values

    lgb_train = lgb.Dataset(X_train, label=y_train)
    lgb_val = lgb.Dataset(X_val, label=y_val, reference=lgb_train)

    params = {
        "objective": "binary",
        "metric": "binary_logloss",
        "learning_rate": 0.05,
        "max_depth": 4,
        "num_leaves": 15,
        "min_data_in_leaf": 200,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 5,
        "lambda_l2": 1.0,  # L2 정규화
        "verbose": -1,
        "n_jobs": -1,
    }

    print("\nTraining LightGBM...")
    t0 = time.time()
    model = lgb.train(
        params,
        lgb_train,
        num_boost_round=500,
        valid_sets=[lgb_train, lgb_val],
        valid_names=["train", "val"],
        callbacks=[lgb.early_stopping(20), lgb.log_evaluation(50)],
    )
    print(f"  trained in {time.time() - t0:.1f}s, best iter {model.best_iteration}")

    # Save model + feature columns
    with open(MODEL_PATH, "wb") as f:
        pickle.dump({"model": model, "features": FEATURE_COLS}, f)
    print(f"  saved -> {MODEL_PATH}")

    # Feature importance
    imp = sorted(zip(FEATURE_COLS, model.feature_importance(importance_type="gain")), key=lambda x: -x[1])
    print("\nTop feature importance (gain):")
    for f, v in imp[:10]:
        print(f"  {f:15s}: {v:>8.0f}")

    return model, train_df, val_df, test_df


# ───────────────────────────────────────────────────────────
# Backtest
# ───────────────────────────────────────────────────────────

def backtest_ml(df=None, model=None, top_n=2, no_reentry_days=60):
    """매일 prediction → top-N → 60일 forward return"""
    if df is None:
        df = pd.read_parquet(FEATURES_PATH)
    if model is None:
        with open(MODEL_PATH, "rb") as f:
            saved = pickle.load(f)
        model = saved["model"]

    test_df = df[df["date"] > VAL_END].dropna(subset=["fwd_ret"]).copy()
    X_test = test_df[FEATURE_COLS].values
    test_df["proba"] = model.predict(X_test, num_iteration=model.best_iteration)

    print(f"\nBacktest on Test set: {len(test_df):,} predictions, dates {test_df['date'].min()} ~ {test_df['date'].max()}")

    # 매일 top-N (no-reentry)
    results = []
    last_entry = {}  # ticker -> last_date_idx
    all_dates = sorted(test_df["date"].unique())
    date_to_idx = {d: i for i, d in enumerate(all_dates)}

    grouped = test_df.groupby("date")
    t0 = time.time()
    for date, group in grouped:
        ranked = group.sort_values("proba", ascending=False)
        di = date_to_idx[date]
        taken = 0
        for _, row in ranked.iterrows():
            if taken >= top_n:
                break
            ticker = row["ticker"]
            le = last_entry.get(ticker)
            if le is not None and (di - le) < no_reentry_days:
                continue
            results.append({
                "date": date, "ticker": ticker,
                "proba": row["proba"], "ret60": row["fwd_ret"],
            })
            last_entry[ticker] = di
            taken += 1

    print(f"  {len(results):,} events in {time.time() - t0:.1f}s")

    if not results:
        print("  NO RESULTS")
        return None

    rets = np.array([r["ret60"] for r in results])
    n = len(rets)
    avg = rets.mean()
    hit = (rets > 0).mean()
    std = rets.std(ddof=1)
    tc_adj = avg - 0.005
    t_stat = avg / (std / np.sqrt(n)) if std > 0 else 0
    sharpe_ann = (avg / std) * np.sqrt(250 / FORWARD) if std > 0 else 0
    n_dates = test_df["date"].nunique()
    avg_per_day = n / n_dates

    print(f"\n=== Test Set Performance (OOS 2023+) ===")
    print(f"  Events: {n:,} / Test dates: {n_dates} / Avg: {avg_per_day:.2f}/day")
    print(f"  60d avg:        {avg*100:+6.2f}%")
    print(f"  60d avg (TC):   {tc_adj*100:+6.2f}%")
    print(f"  Hit rate:       {hit*100:5.1f}%")
    print(f"  Std:            {std*100:+6.2f}%")
    print(f"  Sharpe (ann):   {sharpe_ann:6.2f}")
    print(f"  t-stat:         {t_stat:6.2f}")

    # By year
    print(f"\n  By year:")
    rdf = pd.DataFrame(results)
    rdf["year"] = pd.to_datetime(rdf["date"]).dt.year
    for y in sorted(rdf["year"].unique()):
        ys = rdf[rdf["year"] == y]
        ya = ys["ret60"].mean()
        yh = (ys["ret60"] > 0).mean()
        yt = ya / (ys["ret60"].std(ddof=1) / np.sqrt(len(ys))) if len(ys) > 1 else 0
        print(f"    [{y}] N={len(ys):>4d} avg={ya*100:+6.2f}% hit={yh*100:5.1f}% t={yt:5.2f}")

    return results


# ───────────────────────────────────────────────────────────
# Live inference (latest date in TS_DIR_LIVE)
# ───────────────────────────────────────────────────────────

def infer_latest(top_n=10):
    """라이브 timeseries에서 최신 날짜의 top-N 종목 예측"""
    # 라이브 timeseries로 features 추출 (해당 종목들만, 최신 날짜)
    df = build_features(ts_dir=TS_DIR_LIVE, save=False)
    latest_date = df["date"].max()
    today = df[df["date"] == latest_date].dropna(subset=FEATURE_COLS)

    with open(MODEL_PATH, "rb") as f:
        saved = pickle.load(f)
    model = saved["model"]

    X = today[FEATURE_COLS].values
    today = today.copy()
    today["proba"] = model.predict(X, num_iteration=model.best_iteration)
    ranked = today.sort_values("proba", ascending=False).head(top_n)
    print(f"\nLatest date: {latest_date}")
    print(f"Top-{top_n} predictions:")
    for _, row in ranked.iterrows():
        print(f"  {row['ticker']}  proba={row['proba']:.3f}")
    return ranked[["ticker", "proba"]].to_dict("records")


# ───────────────────────────────────────────────────────────
# Main
# ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--features", action="store_true")
    parser.add_argument("--train", action="store_true")
    parser.add_argument("--backtest", action="store_true")
    parser.add_argument("--infer", action="store_true")
    parser.add_argument("--top-n", type=int, default=2)
    args = parser.parse_args()

    if args.features:
        build_features()
        return
    if args.train:
        train_model()
        return
    if args.backtest:
        backtest_ml(top_n=args.top_n)
        return
    if args.infer:
        infer_latest(top_n=10)
        return

    # 전체 흐름
    print("=" * 60)
    print("AI 판별 수급 주도주 - Full pipeline")
    print("=" * 60)

    if not FEATURES_PATH.exists():
        print("\n>>> Step 1: Build features")
        build_features()
    else:
        print(f"\n>>> Step 1: features 이미 있음 ({FEATURES_PATH})")

    print("\n>>> Step 2: Train")
    train_model()

    print("\n>>> Step 3: Backtest (top-2, no-reentry)")
    backtest_ml(top_n=2)

    print("\n>>> Step 4: Backtest (top-5, no-reentry)")
    backtest_ml(top_n=5)


if __name__ == "__main__":
    mp.freeze_support()
    main()
