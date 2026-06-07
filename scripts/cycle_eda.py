"""
Phase 1: 사이클 EDA (Exploratory Data Analysis)

목적: 섹터별 시계열 + 수급 flow 데이터를 만들고, 사이클 분석 가능성 검증.

데이터 source:
- scripts/backtest_data/timeseries/*.json (10년치 종목별 시계열)
- public/data/sector-map.json (ticker -> sector_mid 매핑)

출력 (콘솔 + scripts/ml_artifacts/cycle_eda_results.json):
1. 섹터별 일별 시총가중 수익률 시계열
2. 섹터별 일별 외인/기관/연기금 flow
3. 섹터별 통계 (평균/std/Sharpe/누적수익률)
4. 섹터 간 correlation matrix
5. KOSPI 대비 섹터별 베타·alpha
6. Phase 2 (HMM regime detection)로 갈 수 있는지 판단 근거

실행:
  python scripts/cycle_eda.py
"""

import json
import multiprocessing as mp
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
TS_DIR = BASE_DIR / "scripts" / "backtest_data" / "timeseries"
SECTOR_MAP_PATH = BASE_DIR / "public" / "data" / "sector-map.json"
ART_DIR = BASE_DIR / "scripts" / "ml_artifacts"
ART_DIR.mkdir(parents=True, exist_ok=True)

OUT_JSON = ART_DIR / "cycle_eda_results.json"
SECTOR_PANEL_PARQUET = ART_DIR / "sector_panel.parquet"


# ──────────────────────────────────────────────────
# Step 1: Load sector mapping
# ──────────────────────────────────────────────────

def load_sector_map():
    if not SECTOR_MAP_PATH.exists():
        print(f"[ERROR] sector-map.json 없음: {SECTOR_MAP_PATH}")
        return {}
    with open(SECTOR_MAP_PATH, "r", encoding="utf-8") as f:
        sm = json.load(f)
    ticker_to_sector = {}
    for ticker, info in sm.items():
        mid = info.get("mid")
        if mid and mid != "기타":
            ticker_to_sector[ticker] = mid
    print(f"  Sector map: {len(ticker_to_sector)} tickers in {len(set(ticker_to_sector.values()))} sectors")
    return ticker_to_sector


# ──────────────────────────────────────────────────
# Step 2: Load timeseries in parallel + flatten to long DataFrame
# ──────────────────────────────────────────────────

def load_one_ticker(args):
    """한 종목 파일 -> long-format DataFrame
    columns: date, ticker, ret, mcap, foreign, inst, pension
    """
    ticker, file_path = args
    try:
        d = json.load(open(file_path, "r", encoding="utf-8"))
    except Exception:
        return None
    dates = d.get("dates", [])
    n = len(dates)
    if n < 30:
        return None
    prices = np.asarray(d.get("prices", []), dtype=np.float64)
    foreign = np.asarray(d.get("foreign", []), dtype=np.float64)
    inst = np.asarray(d.get("inst", []), dtype=np.float64)
    pension = np.asarray(d.get("pension", []), dtype=np.float64)
    mcap = np.asarray(d.get("market_cap", []), dtype=np.float64)
    if len(prices) != n or len(mcap) != n:
        return None
    # daily return (close-to-close)
    ret = np.full(n, np.nan)
    for i in range(1, n):
        if prices[i] > 0 and prices[i - 1] > 0:
            ret[i] = prices[i] / prices[i - 1] - 1
    df = pd.DataFrame({
        "date": dates,
        "ticker": ticker,
        "ret": ret,
        "mcap": mcap,
        "foreign": foreign,
        "inst": inst,
        "pension": pension,
    })
    return df


def build_panel(ticker_to_sector):
    """모든 종목 -> long DataFrame + sector 매핑"""
    files = [f for f in TS_DIR.glob("*.json") if f.stem != "_index"]
    args = []
    for f in files:
        t = f.stem
        if t not in ticker_to_sector:
            continue  # sector 매핑 없는 종목 제외
        args.append((t, f))
    print(f"  Loading {len(args)} ticker timeseries (parallel, workers={mp.cpu_count()})...")
    t0 = time.time()
    with mp.Pool(processes=mp.cpu_count()) as pool:
        results = pool.map(load_one_ticker, args, chunksize=20)
    dfs = [r for r in results if r is not None]
    df = pd.concat(dfs, ignore_index=True)
    # sector 컬럼 추가
    df["sector"] = df["ticker"].map(ticker_to_sector)
    df = df.dropna(subset=["sector"])
    print(f"  Panel: {len(df):,} rows (date x ticker), {df['ticker'].nunique()} tickers, {df['sector'].nunique()} sectors ({time.time()-t0:.1f}s)")
    return df


# ──────────────────────────────────────────────────
# Step 3: Aggregate by sector x date
# ──────────────────────────────────────────────────

def aggregate_sector_panel(df):
    """섹터별 일별 집계:
    - 시총가중 수익률
    - 외인/기관/연기금 flow 합계 (백만원)
    - 종목 수
    - 합계 시총
    """
    print("  Aggregating sector x date panel...")
    t0 = time.time()
    df = df.copy()
    df["mcap_x_ret"] = df["mcap"] * df["ret"]
    grouped = df.groupby(["date", "sector"]).agg(
        mcap_sum=("mcap", "sum"),
        mcap_x_ret_sum=("mcap_x_ret", "sum"),
        foreign_sum=("foreign", "sum"),
        inst_sum=("inst", "sum"),
        pension_sum=("pension", "sum"),
        n_stocks=("ticker", "count"),
    ).reset_index()
    grouped["sector_ret"] = np.where(
        grouped["mcap_sum"] > 0,
        grouped["mcap_x_ret_sum"] / grouped["mcap_sum"],
        np.nan,
    )
    grouped = grouped.drop(columns=["mcap_x_ret_sum"])
    print(f"  Sector panel: {len(grouped):,} rows ({grouped['date'].nunique()} dates x {grouped['sector'].nunique()} sectors) {time.time()-t0:.1f}s")
    return grouped


# ──────────────────────────────────────────────────
# Step 4: Sector statistics
# ──────────────────────────────────────────────────

def compute_sector_stats(sector_df):
    """섹터별 (전체 기간) 통계"""
    stats = []
    for sec, g in sector_df.groupby("sector"):
        g = g.sort_values("date")
        rets = g["sector_ret"].dropna().values
        if len(rets) < 30:
            continue
        cum_ret = np.prod(1 + rets) - 1
        mean = rets.mean()
        std = rets.std(ddof=1)
        sharpe_ann = (mean / std) * np.sqrt(250) if std > 0 else 0
        # 외인/기관/연기금 누적 (백만원 -> 조원)
        f_total = g["foreign_sum"].sum() / 1_000_000
        i_total = g["inst_sum"].sum() / 1_000_000
        p_total = g["pension_sum"].sum() / 1_000_000
        # 평균 시총 (백억원)
        avg_mcap = g["mcap_sum"].mean() / 1e10
        stats.append({
            "sector": sec,
            "n_days": len(rets),
            "cum_return": float(cum_ret),
            "ann_mean": float(mean * 250),
            "ann_std": float(std * np.sqrt(250)),
            "sharpe_ann": float(sharpe_ann),
            "avg_mcap_100억": float(avg_mcap),
            "foreign_cum_조원": float(f_total),
            "inst_cum_조원": float(i_total),
            "pension_cum_조원": float(p_total),
        })
    stats_df = pd.DataFrame(stats).sort_values("sharpe_ann", ascending=False).reset_index(drop=True)
    return stats_df


# ──────────────────────────────────────────────────
# Step 5: Sector correlation matrix
# ──────────────────────────────────────────────────

def compute_correlations(sector_df):
    """섹터 간 일별 수익률 correlation"""
    pivot = sector_df.pivot(index="date", columns="sector", values="sector_ret")
    corr = pivot.corr()
    return corr


# ──────────────────────────────────────────────────
# Step 6: Flow leading indicator check
# ──────────────────────────────────────────────────

def flow_leading_analysis(sector_df, max_lag=20):
    """외인 flow가 sector return 을 leading 하는지 (cross-correlation)"""
    results = {}
    for sec, g in sector_df.groupby("sector"):
        g = g.sort_values("date").reset_index(drop=True)
        rets = g["sector_ret"].values
        for_flow = g["foreign_sum"].values / 1_000_000  # 조원 단위
        # Lag k: corr(foreign_flow[t], sector_ret[t+k])
        valid = (~np.isnan(rets)) & (~np.isnan(for_flow))
        rets_v = rets[valid]
        for_v = for_flow[valid]
        if len(rets_v) < 60:
            continue
        lag_corr = {}
        for k in range(-max_lag, max_lag + 1):
            if k == 0:
                lag_corr[k] = float(np.corrcoef(for_v, rets_v)[0, 1])
            elif k > 0:  # 외인 flow leads return by k days
                if len(for_v) > k:
                    lag_corr[k] = float(np.corrcoef(for_v[:-k], rets_v[k:])[0, 1])
            else:
                if len(rets_v) > -k:
                    lag_corr[k] = float(np.corrcoef(for_v[-k:], rets_v[:k])[0, 1])
        # Find max positive lag (foreign leads return)
        best_lag = max(lag_corr, key=lambda x: lag_corr[x])
        results[sec] = {
            "best_lag_days": int(best_lag),
            "best_lag_corr": lag_corr[best_lag],
            "contemporaneous": lag_corr.get(0, np.nan),
        }
    return results


# ──────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────

def main():
    print("=" * 70)
    print("Cycle EDA - Phase 1")
    print("=" * 70)

    print("\n[Step 1] Loading sector map...")
    ticker_to_sector = load_sector_map()
    if not ticker_to_sector:
        print("[ERROR] No sector mapping. Run scripts/fetch_wics.py first.")
        return

    print("\n[Step 2] Loading timeseries panel...")
    df = build_panel(ticker_to_sector)
    if df.empty:
        print("[ERROR] Empty panel.")
        return

    print("\n[Step 3] Aggregating sector x date panel...")
    sector_df = aggregate_sector_panel(df)
    sector_df.to_parquet(SECTOR_PANEL_PARQUET, compression="snappy")
    print(f"  Saved sector panel -> {SECTOR_PANEL_PARQUET}")

    print("\n[Step 4] Sector statistics (10y)...")
    stats_df = compute_sector_stats(sector_df)
    print()
    print(stats_df.to_string(index=False))

    print("\n[Step 5] Sector correlation matrix (10y)...")
    corr = compute_correlations(sector_df)
    print(corr.round(2).to_string())

    print("\n[Step 6] Foreign flow leading return analysis...")
    lead = flow_leading_analysis(sector_df)
    print()
    print(f"  {'Sector':<25s} {'BestLag':>8s} {'BestCorr':>10s} {'Same-day':>10s}")
    for sec, r in sorted(lead.items(), key=lambda x: -x[1]["best_lag_corr"]):
        sign = "(외인 선행)" if r["best_lag_days"] > 0 else "(동시/후행)" if r["best_lag_days"] >= 0 else "(외인 후행)"
        print(f"  {sec:<25s} {r['best_lag_days']:+>8d} {r['best_lag_corr']:+>10.3f} {r['contemporaneous']:+>10.3f}  {sign}")

    # ──────────────────────────────────────────────
    # 저장
    # ──────────────────────────────────────────────
    out = {
        "summary": {
            "n_tickers": int(df["ticker"].nunique()),
            "n_sectors": int(df["sector"].nunique()),
            "n_dates": int(sector_df["date"].nunique()),
            "date_range": [sector_df["date"].min(), sector_df["date"].max()],
        },
        "sector_stats": stats_df.to_dict("records"),
        "correlations": {
            sec1: {sec2: float(corr.loc[sec1, sec2]) for sec2 in corr.columns}
            for sec1 in corr.index
        },
        "flow_leading": lead,
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\nOK saved -> {OUT_JSON}")

    # ──────────────────────────────────────────────
    # 판단 근거 (Phase 2 진행 가치)
    # ──────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("Phase 2 (HMM regime detection) 진행 가치 검토")
    print("=" * 70)

    n_sectors = df["sector"].nunique()
    high_corr_pairs = []
    for s1 in corr.index:
        for s2 in corr.columns:
            if s1 < s2:
                c = corr.loc[s1, s2]
                if c < 0.5:  # 낮은 correlation = 사이클 분리 의미 있음
                    high_corr_pairs.append((s1, s2, float(c)))
    high_corr_pairs.sort(key=lambda x: x[2])

    leading_sectors = [s for s, r in lead.items() if r["best_lag_days"] > 0 and r["best_lag_corr"] > 0.2]

    print(f"\n1. 섹터 수: {n_sectors}개 (사이클 분석에 최소 5개 권장 -> {'OK' if n_sectors >= 5 else '부족'})")
    print(f"2. 데이터 기간: {sector_df['date'].nunique()}일 ({'OK' if sector_df['date'].nunique() >= 1000 else '부족'} >= 1000일)")
    print(f"3. 섹터 분리도 (corr < 0.5인 pair): {len(high_corr_pairs)}개 ({'좋음' if len(high_corr_pairs) >= 3 else '제한적'})")
    print(f"4. 외인 leading sector (best lag > 0, corr > 0.2): {len(leading_sectors)}개 ({'발견' if leading_sectors else '없음'})")
    if leading_sectors:
        print(f"   - {', '.join(leading_sectors[:5])}")

    print()
    if n_sectors >= 5 and sector_df["date"].nunique() >= 1000 and len(high_corr_pairs) >= 3:
        print(">> Phase 2 (HMM regime detection) 진행 권장: 데이터 충분 + 섹터 분리 의미 있음")
    else:
        print(">> Phase 2 보류: 데이터 부족 또는 섹터 너무 동조 (regime 분리 어려울 수 있음)")


if __name__ == "__main__":
    mp.freeze_support()
    main()
