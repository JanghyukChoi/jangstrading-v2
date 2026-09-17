"""
과거 스냅샷에 **개인·기타법인 순매수**를 채워 넣는다.

왜 필요한가
  기존 스냅샷은 외국인·기관·연기금만 들고 있다. 그런데 하려는 두 가지가
  이 둘을 필요로 한다.

    개인(prsn)      — 체결 타이밍 분해. 개인 순매수가 '어제 오른 종목을
                      오늘 눌릴 때' 들어갔는지를 재려면 종목별 개인 금액이
                      있어야 한다. 시장 합계로는 안 된다.
    기타법인(etc_corp) — 자사주 매입·계열사 지분·M&A 축적. KRX 분류에서
                      내부자에 가장 가까운 매수 주체다.

  둘 다 KIS 투자자매매동향 응답에 **이미 들어 있다**. 우리가 버리고 있었을 뿐이라
  앞으로는 추가 호출이 없다(kis_fetch 가 수집하도록 고쳤다). 과거분만 채우면 된다.

비용
  한 호출이 30 영업일. 10년(약 2,520영업일)이면 종목당 84회.
  2,700종목 x 84 = 약 227,000회, 초당 6건이면 **약 10.5시간**.
  중단되면 --resume 으로 이어서 한다(종목 단위로 완료 표시를 남긴다).

중단 대비 설계
  1. **시총 큰 종목부터** 처리한다. 중간에 멈춰도 거래대금 대부분이 확보된다.
     (전체의 절반만 돼도 시장 수급의 대부분을 덮는다)
  2. `--stop-at HH:MM` 으로 예약 종료. 매일 17:10 에 도는 크론과 KIS 유량을
     나눠 쓰면 둘 다 느려진다 — 실측으로 크론이 1시간 24분 걸리는데 타임아웃이
     120분이라 여유가 36분뿐이다. 겹치기 전에 스스로 비킨다.
  3. 종목 단위 `--resume`. 50종목마다 진행상황을 저장한다.

실행
  python scripts/backfill_flows.py --start 2016-02-19 --stop-at 16:30
  python scripts/backfill_flows.py --resume --stop-at 16:30   # 이어서
  python scripts/backfill_flows.py --limit 20                 # 테스트
"""

import argparse
import json
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kis_api import KisClient, KisError  # noqa: E402
from kis_fetch import (  # noqa: E402
    BASE_DIR, DATA_DIR, INVESTOR_TR, INVESTOR_URL, load_universe, ntby_pbmn,
)

OUT_DIR = BASE_DIR / "scripts" / "backtest_data" / "flows"
STATE_PATH = OUT_DIR / "_progress.json"
ROWS_PER_CALL = 30


def fetch_flows(kis, ticker, start_ymd, end_ymd):
    """기간 전체의 (날짜 -> [개인, 기타법인]) 백만원. 날짜 내림차순으로 거슬러 올라간다."""
    out = {}
    cursor = end_ymd
    start_dt = datetime.strptime(start_ymd, "%Y%m%d")
    guard = 0
    while guard < 200:
        guard += 1
        body = kis.get(
            INVESTOR_URL,
            tr_id=INVESTOR_TR,
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": ticker,
                "FID_INPUT_DATE_1": cursor,
                "FID_ORG_ADJ_PRC": "",
                "FID_ETC_CLS_CODE": "",
            },
        )
        rows = body.get("output2") or []
        if isinstance(rows, dict):
            rows = [rows]
        rows = [r for r in rows if str(r.get("stck_clpr", "")).strip()]
        if not rows:
            break

        for r in rows:
            d = r["stck_bsop_date"]
            # 개인·기타법인 대금(백만원). 없으면 0.
            out[d] = [ntby_pbmn(r, "prsn"), ntby_pbmn(r, "etc_corp")]

        oldest = min(r["stck_bsop_date"] for r in rows)
        if datetime.strptime(oldest, "%Y%m%d") <= start_dt:
            break
        cursor = (datetime.strptime(oldest, "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d")
    return {d: v for d, v in out.items() if d >= start_ymd}


def order_by_mcap(universe):
    """시총 내림차순. 중간에 멈춰도 중요한 종목이 먼저 끝나도록.

    stock-rankings.json 의 market_cap(억원)을 쓴다. 없는 종목은 뒤로 보낸다.
    """
    caps = {}
    try:
        rk = json.loads((DATA_DIR / "stock-rankings.json").read_text(encoding="utf-8"))
        caps = {s["ticker"]: (s.get("market_cap") or 0) for s in rk["data"] if s.get("ticker")}
    except (OSError, ValueError, KeyError):
        return universe
    return sorted(universe, key=lambda s: -caps.get(s["ticker"], 0))


def parse_stop_at(v):
    """'16:30' -> 오늘(또는 내일) 그 시각의 epoch. 빈 값이면 None."""
    if not v:
        return None
    hh, mm = (int(x) for x in v.split(":"))
    now = datetime.now()
    t = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if t <= now:
        t += timedelta(days=1)
    return t


def load_progress():
    try:
        return set(json.loads(STATE_PATH.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return set()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2016-02-19", help="시작일 YYYY-MM-DD 또는 YYYYMMDD")
    ap.add_argument("--end", default="", help="종료일 (기본: 최근 확정일)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--stop-at", default="", metavar="HH:MM",
                    help="이 시각이 되면 진행상황을 저장하고 멈춘다 (크론 회피)")
    args = ap.parse_args()

    stop_at = parse_stop_at(args.stop_at)

    start_ymd = args.start.replace("-", "")
    end_ymd = args.end.replace("-", "") or (
        datetime.now() - timedelta(days=1)).strftime("%Y%m%d")

    kis = KisClient()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    universe = order_by_mcap(load_universe(args.limit or None))
    done = load_progress() if args.resume else set()
    todo = [s for s in universe if s["ticker"] not in done]

    calls = -(-2520 // ROWS_PER_CALL)
    print("=" * 62)
    print(f"개인·기타법인 백필  {start_ymd} ~ {end_ymd}")
    print(f"  전체 {len(universe)}종목 / 남은 {len(todo)}종목")
    print(f"  종목당 최대 {calls}회 · 예상 {len(todo)*calls/6/3600:.1f}시간")
    print("  시총 큰 종목부터 진행 (중단 시 중요 종목이 먼저 확보되도록)")
    if stop_at:
        print(f"  예약 종료: {stop_at:%Y-%m-%d %H:%M} "
              f"({(stop_at - datetime.now()).total_seconds()/3600:.1f}시간 뒤)")
    print("=" * 62)

    lock = threading.Lock()
    t0 = time.monotonic()
    counter = {"n": 0, "ok": 0, "fail": 0, "rows": 0}
    progress = set(done)

    stopped = {"flag": False}

    def work(stock):
        tk = stock["ticker"]
        if stopped["flag"]:
            return tk, None
        if stop_at and datetime.now() >= stop_at:
            stopped["flag"] = True
            return tk, None
        try:
            flows = fetch_flows(kis, tk, start_ymd, end_ymd)
        except (KisError, Exception):
            return tk, None
        return tk, flows

    def save_progress():
        STATE_PATH.write_text(json.dumps(sorted(progress)), encoding="utf-8")

    import concurrent.futures as cf
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for tk, flows in pool.map(work, todo):
            with lock:
                if stopped["flag"] and not flows:
                    continue
                counter["n"] += 1
                if flows:
                    (OUT_DIR / f"{tk}.json").write_text(
                        json.dumps(flows, separators=(",", ":")), encoding="utf-8")
                    progress.add(tk)
                    counter["ok"] += 1
                    counter["rows"] += len(flows)
                else:
                    counter["fail"] += 1
                if counter["n"] % 50 == 0:
                    save_progress()
                if counter["n"] % 200 == 0 or counter["n"] == len(todo):
                    el = time.monotonic() - t0
                    rate = counter["n"] / el if el else 0
                    eta = (len(todo) - counter["n"]) / rate / 3600 if rate else 0
                    print(f"  {counter['n']}/{len(todo)}  성공 {counter['ok']}  "
                          f"실패 {counter['fail']}  행 {counter['rows']:,}  "
                          f"경과 {el/3600:.1f}h  남은 ~{eta:.1f}h")
    save_progress()

    if stopped["flag"]:
        print(f"\n  예약 종료 시각({args.stop_at}) 도달 — 진행상황 저장하고 멈춥니다.")
        print(f"  이어서: python scripts/backfill_flows.py --resume --start {start_ymd}")

    files = list(OUT_DIR.glob("*.json"))
    size = sum(f.stat().st_size for f in files if f.name != "_progress.json")
    print(f"\n  {len(files)-1}개 종목 / {size/1024/1024:.0f}MB / "
          f"총 소요 {(time.monotonic()-t0)/3600:.1f}시간")
    return 0


if __name__ == "__main__":
    sys.exit(main())
