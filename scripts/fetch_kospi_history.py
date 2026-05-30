"""
KOSPI 지수 종가 시계열 캐시

출력: public/data/kospi-history.json — {"2026-05-29": 2734.12, ...}

용도:
- build_v3_signals.py의 regime filter (KOSPI 60일 모멘텀) 정확도 보장
- snapshot.market.kospi는 save_snapshot 시작 이후만 있어 60일치 부족할 수 있음

실행:
  python scripts/fetch_kospi_history.py            # 점진 갱신 (마지막 날짜 이후만)
  python scripts/fetch_kospi_history.py --days 200 # 강제 200일치 backfill
"""

import argparse
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from pykrx import stock  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent
OUT_PATH = BASE_DIR / "public" / "data" / "kospi-history.json"

KOSPI_TICKER = "1001"  # KOSPI 종합지수
MIN_HISTORY = 80       # 60일 모멘텀 + 여유


def fetch_range(start_date, end_date):
    """pykrx로 KOSPI 종가 fetch. 반환: {YYYY-MM-DD: close}"""
    s = start_date.strftime("%Y%m%d")
    e = end_date.strftime("%Y%m%d")
    df = stock.get_index_ohlcv(s, e, KOSPI_TICKER)
    out = {}
    if df is None or df.empty:
        return out
    for ts, row in df.iterrows():
        date_str = ts.strftime("%Y-%m-%d")
        close = row.get("종가")
        if close and close > 0:
            out[date_str] = float(close)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=None, help="강제 N일치 backfill (기본: 점진 갱신)")
    args = parser.parse_args()

    # 기존 데이터 로드
    existing = {}
    if OUT_PATH.exists():
        try:
            existing = json.load(open(OUT_PATH, "r", encoding="utf-8"))
        except Exception:
            existing = {}

    today = datetime.now().date()

    if args.days or not existing or len(existing) < MIN_HISTORY:
        # 전체/큰 범위 backfill
        days = args.days or MIN_HISTORY + 20
        start = today - timedelta(days=days * 1.7)  # 영업일 여유 + 주말
        print(f"Backfill: {start} ~ {today} (~{days} 영업일 목표)")
        new_data = fetch_range(start, today)
    else:
        # 점진: 마지막 날짜 이후만
        last_date = max(existing.keys())
        last_dt = datetime.strptime(last_date, "%Y-%m-%d").date()
        if last_dt >= today:
            print(f"이미 최신: {last_date}")
            return
        start = last_dt + timedelta(days=1)
        print(f"점진 갱신: {start} ~ {today}")
        new_data = fetch_range(start, today)

    merged = {**existing, **new_data}
    print(f"  Fetched: {len(new_data)}일, Total cache: {len(merged)}일")
    if merged:
        sorted_dates = sorted(merged.keys())
        print(f"  Range: {sorted_dates[0]} ~ {sorted_dates[-1]}")

    # Atomic write
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, separators=(",", ":"))
    import os
    os.replace(tmp, OUT_PATH)
    size_kb = OUT_PATH.stat().st_size / 1024
    print(f"OK {OUT_PATH.name} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
