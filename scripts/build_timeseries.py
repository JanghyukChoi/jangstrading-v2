"""
종목별 시계열 데이터 빌드

입력: public/data/snapshots/*.json (일별 스냅샷, 종목별 일별 순매수)
출력: public/data/timeseries/{ticker}.json (종목당 1 파일)
      public/data/timeseries/_index.json (사용 가능한 ticker 목록 + 범위)

목적:
- 종목 상세 페이지에서 외국인/기관 누적 순매수 라인 차트 그릴 때
  한 파일만 fetch하면 됨 (250개 snapshot 파일 일일이 안 받아도 됨)

실행:
  python scripts/build_timeseries.py
"""

import json
import time
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "public" / "data"
SNAP_DIR = DATA_DIR / "snapshots"
OUT_DIR = DATA_DIR / "timeseries"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def main():
    t0 = time.time()
    snap_files = sorted(SNAP_DIR.glob("*.json"))
    print(f"=== 시계열 빌드 시작 ===")
    print(f"입력 스냅샷: {len(snap_files)}개")

    if not snap_files:
        print("[ERROR] 스냅샷 파일이 없습니다.")
        return

    # ticker별 시계열 수집
    # data[ticker] = {dates: [], foreign: [], inst: [], pension: [], prices: []}
    data = defaultdict(lambda: {
        "dates": [],
        "foreign": [],
        "inst": [],
        "pension": [],
        "prices": [],
    })

    dates_processed = []

    for snap_path in snap_files:
        try:
            with open(snap_path, "r", encoding="utf-8") as f:
                snap = json.load(f)
        except Exception as e:
            print(f"  [WARN] {snap_path.name} 읽기 실패: {e}")
            continue

        date = snap.get("date", snap_path.stem)
        foreign_1d = snap.get("foreign_1d", {})
        inst_1d = snap.get("inst_1d", {})
        pension_1d = snap.get("pension_1d", {})
        prices = snap.get("prices", {})

        if not foreign_1d and not inst_1d:
            # 이 날 백필 안 된 상태 - 건너뛰기
            continue

        dates_processed.append(date)

        # 이 날 데이터가 있는 모든 ticker 합집합
        all_tickers = set(foreign_1d.keys()) | set(inst_1d.keys()) | set(pension_1d.keys()) | set(prices.keys())

        for ticker in all_tickers:
            row = data[ticker]
            row["dates"].append(date)
            row["foreign"].append(foreign_1d.get(ticker, 0))
            row["inst"].append(inst_1d.get(ticker, 0))
            row["pension"].append(pension_1d.get(ticker, 0))
            row["prices"].append(prices.get(ticker, 0))

    print(f"수집된 영업일: {len(dates_processed)}일")
    print(f"  범위: {dates_processed[0] if dates_processed else '없음'} ~ {dates_processed[-1] if dates_processed else '없음'}")
    print(f"종목 수: {len(data)}개")

    # 종목별 파일 저장
    saved_count = 0
    skipped_count = 0
    total_size = 0

    for ticker, row in data.items():
        # 데이터가 너무 적은 종목은 스킵 (5일 미만)
        if len(row["dates"]) < 5:
            skipped_count += 1
            continue

        out_path = OUT_DIR / f"{ticker}.json"
        payload = {
            "ticker": ticker,
            **row,
        }
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        total_size += out_path.stat().st_size
        saved_count += 1

    # 인덱스 파일 (UI에서 사용 가능 종목 확인용)
    index = {
        "tickers": sorted(data.keys()),
        "dates_range": {
            "start": dates_processed[0] if dates_processed else None,
            "end": dates_processed[-1] if dates_processed else None,
            "count": len(dates_processed),
        },
    }
    index_path = OUT_DIR / "_index.json"
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, separators=(",", ":"))

    elapsed = time.time() - t0
    print()
    print(f"=== 빌드 완료 ===")
    print(f"  저장: {saved_count}개 파일 (스킵 {skipped_count}개 - 5일 미만)")
    print(f"  총 크기: {total_size / 1024 / 1024:.1f} MB")
    print(f"  평균 파일 크기: {total_size / saved_count / 1024:.1f} KB" if saved_count else "")
    print(f"  인덱스: {index_path.name}")
    print(f"  소요: {elapsed:.1f}초")


if __name__ == "__main__":
    main()
