"""
회전율 가중 기준가격 상태를 깊은 이력으로 한 번 만들어 둔다.

왜 필요한가: 150 영업일로는 모자란다. 삼성전자는 150 일 전 매수분이 아직 55%
살아있어서, 의미 있는 이력의 절반 이상이 잘린 채 계산된다. 기준가가 현재가에
붙어버린다. 원 논문(Grinblatt & Han 2005)은 5 년을 쓰고 3~7 년에 결과가 안정적이라고
보고한다. 감쇠율로 역산하면 최소 2.5~3 년이 필요하다.

한 번만 돌리면 된다. 기준가격은 상태 두 개(num, den)로 증분 갱신이 되므로
(cost_basis.advance 참고) 이후로는 매일 하루치만 반영하면 충분하고, 원시 이력을
보관할 필요도 없다.

출력: public/data/cost-basis.json
    {"updated_through": "YYYY-MM-DD", "data": {ticker: {"f": state, "i": state}}}
    state = {"n": num, "d": den, "b": {price_bin: weight}}

비용: 종목당 depth 회 호출. 기본 25 회(=750 영업일) x 약 2,700 종목 = 약 68,000 회.
      초당 6 건 기준 약 3 시간. 중단되면 --resume 으로 이어서 할 수 있다.

실행:
  python scripts/build_cost_basis.py                    # 전 종목, 750영업일
  python scripts/build_cost_basis.py --depth 42         # 5년
  python scripts/build_cost_basis.py --limit 20         # 테스트
  python scripts/build_cost_basis.py --resume           # 중단 지점부터
"""

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cost_basis as cb  # noqa: E402
from kis_api import KisClient, KisError  # noqa: E402
from kis_fetch import (  # noqa: E402
    DATA_DIR,
    fetch_fundamentals,
    fetch_history,
    latest_business_day,
    load_universe,
)

OUT_PATH = DATA_DIR / "cost-basis.json"


def build_state(rows, holdings_now, shares_outstanding):
    """한 종목의 외국인·기관 상태를 이력 전체로 한 번에 만든다."""
    out = {}
    for group, key in (("foreign", "f"), ("institution", "i")):
        prefix = cb.GROUPS[group]
        series = cb._series(rows, prefix)
        holdings = (
            cb._holdings_path(series, holdings_now)
            if group == "foreign" and holdings_now > 0
            else [0] * len(series)
        )
        st = cb.new_state()
        for i, r in enumerate(rows):
            ex = cb.exit_rate_for(group, r, series[i], holdings[i], shares_outstanding)
            cb.advance(st, ex, series[i]["buy"], series[i]["price"])
        if st["d"] > 0:
            out[key] = st
    return out


def survival_at_start(rows, holdings_now, shares_outstanding):
    """가장 오래된 매수분의 생존 가중치. 0 에 가까울수록 이력이 충분하다."""
    series = cb._series(rows, "frgn")
    holdings = cb._holdings_path(series, holdings_now) if holdings_now > 0 else [0] * len(series)
    acc = 1.0
    for i in range(len(rows) - 1, -1, -1):
        acc *= 1.0 - min(1.0, cb.exit_rate_for("foreign", rows[i], series[i], holdings[i], shares_outstanding))
    return acc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--depth", type=int, default=25,
                    help="종목당 호출 수 (1회=30영업일). 기본 25 = 750영업일 ≈ 3년")
    ap.add_argument("--date", default="", help="기준일 YYYYMMDD (기본: 최근 영업일)")
    ap.add_argument("--limit", type=int, default=0, help="상위 N 종목만 (테스트)")
    ap.add_argument("--resume", action="store_true", help="기존 결과에 이어서")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--workers", type=int, default=6,
                    help="동시 스레드 수. 레이트리미터는 공유되므로 초당 호출 수는 "
                         "그대로고, 왕복 지연만 겹쳐서 숨긴다")
    args = ap.parse_args()

    kis = KisClient()
    date_str = args.date or latest_business_day(kis)
    date_iso = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"

    print("=" * 60)
    print(f"기준가격 상태 구축  기준일={date_iso}  depth={args.depth} (~{args.depth*30}영업일)")
    print("=" * 60)

    existing = {}
    if args.resume and OUT_PATH.exists():
        try:
            existing = json.loads(OUT_PATH.read_text(encoding="utf-8")).get("data", {})
            print(f"  기존 {len(existing)}종목에 이어서 진행")
        except ValueError:
            pass

    universe = load_universe(args.limit or None)
    todo = [s for s in universe if s["ticker"] not in existing]
    print(f"  전체 {len(universe)}종목 / 남은 {len(todo)}종목")
    print(f"  예상 {len(todo) * (args.depth + 1) / 6 / 60:.0f}분\n")

    result = dict(existing)
    surv = []
    failed = 0
    done = 0
    t0 = time.monotonic()
    lock = threading.Lock()

    def work(stock):
        """한 종목 수집 + 상태 계산. KisClient 의 레이트리미터가 전역 유량을
        지키므로 스레드를 늘려도 초당 호출 수는 그대로다. 늘어나는 건 대기시간
        겹치기뿐이다 — 병목이 유량이 아니라 왕복 지연이라 이게 먹는다."""
        ticker = stock["ticker"]
        try:
            rows = fetch_history(kis, ticker, date_str, args.depth, not args.no_cache)
            fund = fetch_fundamentals(kis, ticker, date_str, not args.no_cache)
        except (KisError, Exception):
            return ticker, None, None
        if not rows:
            return ticker, None, None
        holdings = cb._i(fund.get("frgn_hldn_qty"))
        shares = cb._i(fund.get("lstn_stcn"))
        st = build_state(rows, holdings, shares)
        sv = (survival_at_start(rows, holdings, shares)
              if holdings > 0 and len(rows) > 300 else None)
        return ticker, st, sv

    def save():
        OUT_PATH.write_text(json.dumps(
            {"updated_through": date_iso, "depth_calls": args.depth, "data": result},
            ensure_ascii=False), encoding="utf-8")

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for ticker, st, sv in pool.map(work, todo):
            with lock:
                done += 1
                if st:
                    result[ticker] = st
                else:
                    failed += 1
                if sv is not None:
                    surv.append(sv)
                if done % 100 == 0 or done == len(todo):
                    el = time.monotonic() - t0
                    eta = (len(todo) - done) / (done / el) / 60 if el else 0
                    print(f"  {done}/{len(todo)}  완료 {len(result)}  실패 {failed}  "
                          f"경과 {el/60:.0f}분  남은시간 ~{eta:.0f}분")
                    save()  # 긴 작업이라 중단돼도 잃지 않게 중간 저장

    OUT_PATH.write_text(json.dumps(
        {"updated_through": date_iso, "depth_calls": args.depth, "data": result},
        ensure_ascii=False), encoding="utf-8")

    print(f"\n  cost-basis.json 저장 ({len(result)}종목, {OUT_PATH.stat().st_size/1024/1024:.1f} MB)")
    if surv:
        surv.sort()
        mid = surv[len(surv) // 2]
        worst = surv[-1]
        print(f"  이력 충분성 — 가장 오래된 매수분 생존 가중치")
        print(f"    중앙값 {mid:.3f} / 최악 {worst:.3f}   "
              f"({'충분' if mid < 0.15 else '더 깊은 이력 필요'})")
    print(f"  총 소요 {(time.monotonic()-t0)/60:.0f}분")
    return 0


if __name__ == "__main__":
    sys.exit(main())
