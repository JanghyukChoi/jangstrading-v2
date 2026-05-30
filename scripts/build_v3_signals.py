"""
V3 시그널 계산기 (라이브)

입력: public/data/timeseries/*.json (종목별 시계열, 시총·거래량 포함)
출력: public/data/signals.json — 4개 V3 시그널 top-15 ticker 리스트

실행: python scripts/build_v3_signals.py

전제: build_timeseries.py가 augment된 snapshots로부터 먼저 실행되어 있어야 함.
      timeseries 파일에 market_cap, trade_value 필드 있어야 V3 작동.
"""

import json
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TS_DIR = BASE_DIR / "public" / "data" / "timeseries"
SNAP_DIR = BASE_DIR / "public" / "data" / "snapshots"
OUT_PATH = BASE_DIR / "public" / "data" / "signals.json"

# backtest_signals.py에서 V3 시그널 함수 + helper 재사용
sys.path.insert(0, str(BASE_DIR / "scripts"))
from backtest_signals import (  # noqa: E402
    signal_buy_reversal_v3,
    signal_sell_reversal_v3,
    signal_leader_v3,
    signal_accumulation_v3,
)


def build_kospi_context():
    """snapshots에서 KOSPI 종가 시계열을 읽어 정확한 mom60 계산용 context 생성.
    backtest의 equal-weighted index 대신 실제 KOSPI index 사용 (라이브용).
    """
    market_index = {}
    for f in sorted(SNAP_DIR.glob("*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                d = json.load(fp)
        except Exception:
            continue
        kospi = (d.get("market") or {}).get("kospi")
        if kospi and kospi > 0:
            market_index[d.get("date", f.stem)] = kospi
    return {
        "market_index": market_index,
        "dates_sorted": sorted(market_index.keys()),
    }


def kospi_momentum_60d(ctx, date):
    """60 영업일 전 대비 KOSPI 모멘텀"""
    ds = ctx["dates_sorted"]
    mi = ctx["market_index"]
    try:
        idx = ds.index(date)
    except ValueError:
        return None
    if idx < 60:
        return None
    cur = mi[date]
    past = mi[ds[idx - 60]]
    if not past or past <= 0:
        return None
    return cur / past - 1

TOP_N = 15

SIGNAL_FNS = {
    "buy_reversal": signal_buy_reversal_v3,
    "sell_reversal": signal_sell_reversal_v3,
    "leader": signal_leader_v3,
    "accumulation": signal_accumulation_v3,
}


def load_timeseries():
    files = [f for f in TS_DIR.glob("*.json") if f.stem != "_index"]
    data = {}
    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fp:
                d = json.load(fp)
            ticker = d.get("ticker") or f.stem
            data[ticker] = d
        except Exception:
            continue
    return data


def main():
    t0 = time.time()
    print("=" * 60)
    print("V3 시그널 빌드 시작")
    print("=" * 60)

    print(f"  timeseries 로드 중... ({TS_DIR})")
    ts = load_timeseries()
    if not ts:
        print("[ERROR] timeseries 없음. build_timeseries.py 먼저 실행 필요.")
        return
    print(f"  종목: {len(ts):,}개")

    # 최신 영업일 찾기 (모든 timeseries에 공통으로 있는 마지막 날짜)
    all_dates = set()
    for d in ts.values():
        for dt in d.get("dates", []):
            all_dates.add(dt)
    if not all_dates:
        print("[ERROR] 영업일 데이터 없음")
        return
    latest_date = sorted(all_dates)[-1]
    print(f"  대상 영업일: {latest_date}")

    # KOSPI context (regime filter용 — 실제 KOSPI index 종가 시계열)
    print("  시장 context 계산 중...")
    kospi_ctx = build_kospi_context()
    print(f"  KOSPI index 일수: {len(kospi_ctx['dates_sorted'])}")
    mom = kospi_momentum_60d(kospi_ctx, latest_date)
    ctx = {"kospi_mom60": mom}
    if mom is not None:
        print(f"  KOSPI 60일 모멘텀: {mom*100:+.2f}%")
    else:
        print(f"  KOSPI 60일 모멘텀: 데이터 부족")

    # 각 시그널별로 모든 종목 점수 계산 → top-15
    print()
    results = {}
    for name, fn in SIGNAL_FNS.items():
        scored = []
        for ticker, data in ts.items():
            dates = data.get("dates", [])
            try:
                idx = dates.index(latest_date)
            except ValueError:
                continue
            score = fn(data, idx, ctx)
            if score is not None and score > 0:
                scored.append((ticker, score))
        scored.sort(key=lambda x: -x[1])
        top = scored[:TOP_N]
        results[name] = [t for t, _ in top]
        print(f"  [{name:14s}] raw {len(scored):4d} → top-{TOP_N}: {len(top)}개")

    output = {
        "date": latest_date,
        "version": "v3",
        "top_n": TOP_N,
        "signals": results,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = OUT_PATH.stat().st_size / 1024
    print()
    print(f"OK {OUT_PATH.name} ({size_kb:.1f} KB) - {time.time() - t0:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
