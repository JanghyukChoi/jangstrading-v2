"""
종목별 일봉 OHLCV 를 public/data/ohlc/{ticker}.json 으로 저장한다.

캔들 차트용. 기존 timeseries/{ticker}.json 은 손대지 않는다 — 거기에 OHLC 를
합치면 파일이 2~3 배가 되어 종목 상세 페이지 로딩이 느려진다. 차트를 여는
사람만 추가로 받도록 파일을 나눈다.

포맷은 병렬 배열 + 날짜 6자리다. 객체 배열보다 40% 작다(21.3 -> 12.5 KB).

    {"t":"005930","d":[241202,...],"o":[...],"h":[...],"l":[...],"c":[...],"v":[...]}

주봉·월봉은 저장하지 않는다. 일봉에서 클라이언트가 즉시 묶을 수 있고,
세 벌을 들고 있으면 용량이 3 배가 된다.

비용: 기간별시세가 한 호출에 100 행을 준다. 1 년치(약 250 영업일)면 종목당 3 회.
      전 종목 약 8,200 회, 초당 6 건 기준 약 25 분. 이후로는 kis_fetch 가
      매일 하루치만 덧붙인다.

실행:
  python scripts/build_ohlc.py                 # 전 종목 1년치
  python scripts/build_ohlc.py --limit 20      # 테스트
  python scripts/build_ohlc.py --resume        # 이어서
  python scripts/build_ohlc.py --days 500      # 2년치
"""

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kis_api import KisClient, KisError  # noqa: E402
from kis_fetch import DATA_DIR, latest_business_day, load_universe, to_int  # noqa: E402

OHLC_DIR = DATA_DIR / "ohlc"
CHART_URL = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
CHART_TR = "FHKST03010100"
ROWS_PER_CALL = 100  # 실측


def fetch_ohlc(kis, ticker, end_ymd, days):
    """end_ymd 에서 days 일치를 거슬러 올라가며 모은다. 날짜 오름차순 dict."""
    rows = {}
    cursor = datetime.strptime(end_ymd, "%Y%m%d")
    # 100 행 = 약 145 달력일. 여유를 두고 창을 잡는다.
    calls = max(1, -(-days // ROWS_PER_CALL) + 1)
    for _ in range(calls):
        start = cursor - timedelta(days=160)
        body = kis.get(
            CHART_URL,
            tr_id=CHART_TR,
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": ticker,
                "FID_INPUT_DATE_1": start.strftime("%Y%m%d"),
                "FID_INPUT_DATE_2": cursor.strftime("%Y%m%d"),
                "FID_PERIOD_DIV_CODE": "D",
                "FID_ORG_ADJ_PRC": "0",
            },
        )
        got = [r for r in (body.get("output2") or [])
               if str(r.get("stck_bsop_date", "")).strip() and to_int(r.get("stck_clpr"))]
        if not got:
            break
        for r in got:
            rows[r["stck_bsop_date"]] = r
        oldest = min(r["stck_bsop_date"] for r in got)
        cursor = datetime.strptime(oldest, "%Y%m%d") - timedelta(days=1)
        if len(rows) >= days:
            break
    return rows


def to_payload(ticker, rows, days):
    ds = sorted(rows)[-days:]
    if not ds:
        return None
    return {
        "t": ticker,
        "d": [int(x[2:]) for x in ds],  # YYMMDD
        "o": [to_int(rows[d]["stck_oprc"]) for d in ds],
        "h": [to_int(rows[d]["stck_hgpr"]) for d in ds],
        "l": [to_int(rows[d]["stck_lwpr"]) for d in ds],
        "c": [to_int(rows[d]["stck_clpr"]) for d in ds],
        "v": [to_int(rows[d]["acml_vol"]) for d in ds],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=250, help="보관 영업일 수 (기본 250 ≈ 1년)")
    ap.add_argument("--date", default="", help="기준일 YYYYMMDD")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--resume", action="store_true", help="이미 있는 파일은 건너뛴다")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    kis = KisClient()
    end_ymd = args.date or latest_business_day(kis)
    OHLC_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print(f"일봉 OHLCV 구축  기준일={end_ymd}  보관 {args.days}영업일")
    print("=" * 60)

    universe = load_universe(args.limit or None)
    todo = universe
    if args.resume:
        todo = [s for s in universe if not (OHLC_DIR / f"{s['ticker']}.json").exists()]
    print(f"  전체 {len(universe)}종목 / 남은 {len(todo)}종목")
    calls = max(1, -(-args.days // ROWS_PER_CALL) + 1)
    print(f"  종목당 {calls}회  예상 {len(todo)*calls/6/60:.0f}분  (workers={args.workers})\n")

    done = ok = failed = 0
    t0 = time.monotonic()
    lock = threading.Lock()

    def work(stock):
        tk = stock["ticker"]
        try:
            rows = fetch_ohlc(kis, tk, end_ymd, args.days)
        except (KisError, Exception):
            return tk, False
        p = to_payload(tk, rows, args.days)
        if not p:
            return tk, False
        (OHLC_DIR / f"{tk}.json").write_text(
            json.dumps(p, separators=(",", ":")), encoding="utf-8")
        return tk, True

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for tk, good in pool.map(work, todo):
            with lock:
                done += 1
                ok += 1 if good else 0
                failed += 0 if good else 1
                if done % 200 == 0 or done == len(todo):
                    el = time.monotonic() - t0
                    eta = (len(todo) - done) / (done / el) / 60 if el else 0
                    print(f"  {done}/{len(todo)}  성공 {ok}  실패 {failed}  "
                          f"경과 {el/60:.0f}분  남은시간 ~{eta:.0f}분")

    files = list(OHLC_DIR.glob("*.json"))
    total = sum(f.stat().st_size for f in files)
    print(f"\n  {len(files)}개 파일, 총 {total/1024/1024:.1f} MB "
          f"(종목당 평균 {total/max(len(files),1)/1024:.1f} KB)")
    print(f"  총 소요 {(time.monotonic()-t0)/60:.0f}분")
    return 0


if __name__ == "__main__":
    sys.exit(main())
