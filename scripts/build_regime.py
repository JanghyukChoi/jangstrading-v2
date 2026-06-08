"""
일일 시장 국면 (regime) 추론 + JSON 저장

cycle_hmm.py로 학습한 HMM 모델로 매일 현재 시장의 regime을 추론.

입력:
- scripts/ml_artifacts/hmm_model.pkl (학습된 HMM 모델)
- scripts/ml_artifacts/sector_panel.parquet (cycle_eda.py 결과) OR
  public/data/timeseries/* + sector-map.json (라이브 데이터)

출력:
- public/data/regime.json
  {
    "date": "2026-05-29",
    "current_regime": {regime: 1, label: "Crisis", ...},
    "history": [{date, regime, label}, ...],  // 최근 252일
    "sectors_by_regime": {regime: [{name, t_stat, avg_60d}, ...]},
    "model_meta": {...},
  }

실행:
  python scripts/build_regime.py
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
# git-tracked 위치 (cron 환경에서도 사용 가능)
MODEL_DIR = BASE_DIR / "scripts" / "ml_models"
MODEL_PATH = MODEL_DIR / "hmm_model.pkl"
REGIME_PANEL_PATH = MODEL_DIR / "regime_panel.parquet"
REGIME_RESULTS_PATH = MODEL_DIR / "regime_results.json"
# 로컬 backtest only (git ignore)
ART_DIR = BASE_DIR / "scripts" / "ml_artifacts"
SECTOR_PANEL_PATH = ART_DIR / "sector_panel.parquet"

OUT_PATH = BASE_DIR / "public" / "data" / "regime.json"

# 라이브 데이터 소스 (cron 통합 시)
LIVE_TS_DIR = BASE_DIR / "public" / "data" / "timeseries"
LIVE_SECTOR_MAP = BASE_DIR / "public" / "data" / "sector-map.json"

HISTORY_DAYS = 252  # 사이트 표시용 (1년)

# 사용자 친화 라벨 (panic 유발 X, 사실 서술)
LABEL_OVERRIDE = {
    0: {"ko": "저변동 안정기", "en": "Quiet"},
    1: {"ko": "고변동 하락기", "en": "Crisis"},
    2: {"ko": "조정기", "en": "Transition"},
    3: {"ko": "강세 안정기", "en": "Bull"},
}


def get_friendly_label(regime: int) -> str:
    info = LABEL_OVERRIDE.get(regime)
    if info:
        return f"{info['en']} ({info['ko']})"
    return f"Regime {regime}"


def per_episode_return(annualized_return: float, avg_duration_days: float) -> float:
    """국면 1회 평균 누적 수익률 = (annualized × duration / 250)
    예: ann_ret -93.5%, duration 26일 → -9.7%
    """
    return annualized_return * avg_duration_days / 250.0


def build_features_from_sector_panel(sector_panel):
    """sector_panel parquet에서 feature 추출 (cycle_hmm.py와 동일 로직)"""
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
        "vol_20d": vol_20d,
        "ret_20d": ret_20d,
        "dispersion_20d": dispersion_20d,
        "flow_z_5d": flow_z,
        "mkt_ret": weighted_ret,
    }).dropna()
    return df


def build_features_from_live():
    """라이브 timeseries에서 sector_panel 만들고 feature 추출.

    cron에 통합되어 매일 실행될 때 사용.
    """
    # sector map 로드
    if not LIVE_SECTOR_MAP.exists():
        return None
    with open(LIVE_SECTOR_MAP, "r", encoding="utf-8") as f:
        sm = json.load(f)
    ticker_to_sector = {}
    for ticker, info in sm.items():
        mid = info.get("mid")
        if mid and mid != "기타":
            ticker_to_sector[ticker] = mid

    # timeseries 로드
    files = [f for f in LIVE_TS_DIR.glob("*.json") if f.stem != "_index"]
    rows = []
    for f in files:
        t = f.stem
        if t not in ticker_to_sector:
            continue
        try:
            d = json.load(open(f, "r", encoding="utf-8"))
        except Exception:
            continue
        dates = d.get("dates", [])
        n = len(dates)
        if n < 30:
            continue
        prices = np.asarray(d.get("prices", []), dtype=np.float64)
        foreign = np.asarray(d.get("foreign", []), dtype=np.float64)
        inst = np.asarray(d.get("inst", []), dtype=np.float64)
        mcap = np.asarray(d.get("market_cap", []), dtype=np.float64)
        if len(prices) != n or len(mcap) != n:
            continue
        ret = np.full(n, np.nan)
        for i in range(1, n):
            if prices[i] > 0 and prices[i - 1] > 0:
                ret[i] = prices[i] / prices[i - 1] - 1
        sec = ticker_to_sector[t]
        for i in range(n):
            if not np.isnan(ret[i]) and mcap[i] > 0:
                rows.append({
                    "date": dates[i], "sector": sec,
                    "ret": ret[i], "mcap": mcap[i],
                    "foreign": foreign[i] if i < len(foreign) else 0,
                    "inst": inst[i] if i < len(inst) else 0,
                })
    df = pd.DataFrame(rows)
    # Aggregate
    df["mcap_x_ret"] = df["mcap"] * df["ret"]
    grouped = df.groupby(["date", "sector"]).agg(
        mcap_sum=("mcap", "sum"),
        mcap_x_ret_sum=("mcap_x_ret", "sum"),
        foreign_sum=("foreign", "sum"),
        inst_sum=("inst", "sum"),
    ).reset_index()
    grouped["sector_ret"] = grouped["mcap_x_ret_sum"] / grouped["mcap_sum"]
    return grouped


def main():
    print("=" * 70)
    print("Build Regime (latest market state inference)")
    print("=" * 70)

    if not MODEL_PATH.exists():
        print(f"[ERROR] {MODEL_PATH} 없음. cycle_hmm.py 먼저 실행.")
        return

    print(f"\n[Step 1] Load HMM model...")
    with open(MODEL_PATH, "rb") as f:
        saved = pickle.load(f)
    model = saved["model"]
    feat_cols = saved["features"]
    n_regimes = saved["n_regimes"]
    # 모델 학습 시 라벨은 무시하고 사용자 친화 라벨 적용
    regime_labels = {r: get_friendly_label(r) for r in range(n_regimes)}
    print(f"  Model: {n_regimes} regimes, features={feat_cols}")
    print(f"  Labels: {regime_labels}")

    # 데이터 source 결정: 라이브 우선, 없으면 backtest
    print(f"\n[Step 2] Build features...")
    if LIVE_TS_DIR.exists() and any(LIVE_TS_DIR.glob("*.json")):
        print(f"  Using live timeseries ({LIVE_TS_DIR})")
        sector_panel = build_features_from_live()
        if sector_panel is None or sector_panel.empty:
            print("  Live data empty, fallback to backtest sector_panel")
            sector_panel = pd.read_parquet(SECTOR_PANEL_PATH)
    elif SECTOR_PANEL_PATH.exists():
        print(f"  Using backtest sector_panel ({SECTOR_PANEL_PATH})")
        sector_panel = pd.read_parquet(SECTOR_PANEL_PATH)
    else:
        print("[ERROR] 데이터 source 없음")
        return

    feat_df = build_features_from_sector_panel(sector_panel)
    print(f"  Features: {len(feat_df)} dates ({feat_df.index.min()} ~ {feat_df.index.max()})")

    # Inference
    print(f"\n[Step 3] Predict regimes...")
    X = feat_df[feat_cols].values
    regimes = model.predict(X)
    feat_df["regime"] = regimes

    # 최신 regime
    latest_date = feat_df.index[-1]
    current_regime = int(regimes[-1])
    current_label = regime_labels.get(current_regime, f"Regime {current_regime}")
    print(f"  Current ({latest_date}): Regime {current_regime} - {current_label}")

    # History: regime_panel.parquet (학습 시 만든 panel)에서 가져오고
    # 라이브 신규 날짜만 append. 라이브 inference history가 짧아도 OK.
    history_records = []
    if REGIME_PANEL_PATH.exists():
        try:
            old_panel = pd.read_parquet(REGIME_PANEL_PATH)
            old_panel = old_panel.sort_values("date")
            for _, row in old_panel.iterrows():
                history_records.append({
                    "date": str(row["date"]),
                    "regime": int(row["regime"]),
                    "label": regime_labels.get(int(row["regime"]), f"Regime {row['regime']}"),
                })
        except Exception as e:
            print(f"  [WARN] regime_panel.parquet 로드 실패: {e}")

    # 라이브 inference의 최근 날짜 추가 (중복 제거)
    seen_dates = {h["date"] for h in history_records}
    for d, r in zip(feat_df.index, feat_df["regime"]):
        d_str = str(d)
        if d_str not in seen_dates:
            history_records.append({
                "date": d_str,
                "regime": int(r),
                "label": regime_labels.get(int(r), f"Regime {r}"),
            })

    # 최근 N일만 사이트에 노출
    history_records.sort(key=lambda x: x["date"])
    history = history_records[-HISTORY_DAYS:]

    # Regime별 sector winners (regime_results.json에서 가져옴)
    sectors_by_regime = {}
    if REGIME_RESULTS_PATH.exists():
        try:
            with open(REGIME_RESULTS_PATH, "r", encoding="utf-8") as f:
                rr = json.load(f)
            for r_data in rr.get("test_sector_performance", []):
                r = r_data["regime"]
                # Top 10 by t-stat (positive)
                sectors_sorted = sorted(
                    [(sec, stats) for sec, stats in r_data["sectors"].items() if stats["t_stat"] > 0],
                    key=lambda x: -x[1]["t_stat"]
                )[:10]
                sectors_by_regime[str(r)] = [
                    {
                        "sector": sec,
                        "avg_20d": stats["avg"],
                        "t_stat": stats["t_stat"],
                        "hit_rate": stats["hit_rate"],
                    }
                    for sec, stats in sectors_sorted
                ]
        except Exception as e:
            print(f"  [WARN] regime_results.json 로드 실패: {e}")

    # Regime별 통계 (Train+Test 합산 stats)
    regime_meta = {}
    if REGIME_RESULTS_PATH.exists():
        with open(REGIME_RESULTS_PATH, "r", encoding="utf-8") as f:
            rr = json.load(f)
        for s in rr.get("train_regime_stats", []):
            r = s["regime"]
            ann_ret = s["annualized_return"]
            dur = s["avg_duration_days"]
            regime_meta[str(r)] = {
                "label": get_friendly_label(r),
                "label_ko": LABEL_OVERRIDE.get(r, {}).get("ko", ""),
                "label_en": LABEL_OVERRIDE.get(r, {}).get("en", f"Regime {r}"),
                "pct_of_time": s["pct_of_time"],
                "avg_duration_days": dur,
                "per_episode_return": per_episode_return(ann_ret, dur),  # 1회 평균 누적 수익률
                # 학술 metric (사이트엔 노출 X, 호환성 위해 유지)
                "annualized_return": ann_ret,
                "annualized_vol": s["annualized_vol"],
                "sharpe": s["sharpe"],
            }

    # Output
    output = {
        "date": str(latest_date),
        "current_regime": {
            "regime": current_regime,
            "label": current_label,
            "label_ko": LABEL_OVERRIDE.get(current_regime, {}).get("ko", ""),
            "label_en": LABEL_OVERRIDE.get(current_regime, {}).get("en", f"Regime {current_regime}"),
            "meta": regime_meta.get(str(current_regime)),
        },
        "history": history,
        "sectors_by_regime": sectors_by_regime,
        "regime_meta": regime_meta,
        "model_meta": {
            "n_regimes": n_regimes,
            "features": feat_cols,
            "labels": {str(k): v for k, v in regime_labels.items()},
        },
        "generated_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = OUT_PATH.stat().st_size / 1024
    print(f"\nOK {OUT_PATH.name} ({size_kb:.1f} KB)")
    print(f"  Current: Regime {current_regime} - {current_label}")


if __name__ == "__main__":
    main()
