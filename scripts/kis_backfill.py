"""
KIS 로 과거 영업일 스냅샷을 백필한다.

2026-07-17 에 KRX 스크래핑이 막히면서 그 뒤로 snapshots/ 가 비어 있다.
종목 상세의 누적 순매수 차트와 build_timeseries / build_v3_signals /
build_regime 가 전부 snapshots 를 읽으므로 이 구멍을 메워야 한다.

KIS 는 한 호출에 30 영업일치를 주므로, 종목당 depth 회만 호출하면 그 구간의
모든 날짜 스냅샷을 한꺼번에 만들 수 있다. (기존 backfill_snapshots.py 는
날짜마다 전 종목을 다시 긁어서 훨씬 비쌌다)

시가총액은 과거 시점 값을 KIS 가 주지 않으므로 상장주수 x 그날 종가로 계산한다.
상장주수는 현재 값이라 그 사이 증자/감자가 있었다면 약간 어긋날 수 있다.

실행:
  python scripts/kis_backfill.py --from 2026-07-17 --to 2026-09-11
  python scripts/kis_backfill.py --from 2026-07-17            # to 기본 = 최근 영업일
  python scripts/kis_backfill.py --from 2026-07-17 --limit 50 # 테스트
  python scripts/kis_backfill.py --from 2026-07-17 --force    # 기존 파일 덮어쓰기
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kis_api import KisClient, KisError  # noqa: E402
from kis_fetch import (  # noqa: E402
    DATA_DIR,
    MAX_SNAPSHOTS,
    fetch_fundamentals,
    fetch_history,
    fetch_market,
    latest_business_day,
    load_universe,
    ntby_pbmn,
    to_float,
    to_int,
)

SNAP_DIR = DATA_DIR / "snapshots"
SNAPSHOT_NAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def iso(ymd):
    return f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", required=True, help="시작일 YYYY-MM-DD")
    ap.add_argument("--to", dest="end", default="", help="종료일 YYYY-MM-DD (기본: 최근 영업일)")
    ap.add_argument("--depth", type=int, default=0,
                    help="종목당 호출 수. 기본은 기간 길이에서 자동 계산")
    ap.add_argument("--limit", type=int, default=0, help="상위 N 종목만 (테스트용)")
    ap.add_argument("--force", action="store_true", help="이미 있는 스냅샷도 덮어쓰기")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--skip-market-cap", action="store_true",
                    help="시가총액 생략 (종목당 1회 호출 절약)")
    args = ap.parse_args()

    cache = not args.no_cache
    kis = KisClient()

    start_ymd = args.start.replace("-", "")
    end_ymd = args.end.replace("-", "") if args.end else latest_business_day(kis)
    if start_ymd > end_ymd:
        raise SystemExit("시작일이 종료일보다 늦습니다.")

    print("=" * 60)
    print(f"KIS 스냅샷 백필  {iso(start_ymd)} ~ {iso(end_ymd)}")
    print("=" * 60)

    print("\n[1/4] 시장 지수/자금흐름")
    market_rows = fetch_market(kis, end_ymd)
    # 날짜 -> {kospi: x, kosdaq: y}
    index_by_date = {}
    for market, rows in market_rows.items():
        for r in rows:
            index_by_date.setdefault(r["stck_bsop_date"], {})[market.lower()] = to_float(
                r.get("bstp_nmix_prpr")
            )

    target_dates = sorted(d for d in index_by_date if start_ymd <= d <= end_ymd)
    if not target_dates:
        raise SystemExit("해당 구간에 영업일이 없습니다.")
    print(f"  대상 영업일 {len(target_dates)}일  ({iso(target_dates[0])} ~ {iso(target_dates[-1])})")

    if not args.force:
        existing = {f.stem for f in SNAP_DIR.glob("*.json") if SNAPSHOT_NAME_RE.match(f.stem)}
        skipped = [d for d in target_dates if iso(d) in existing]
        target_dates = [d for d in target_dates if iso(d) not in existing]
        if skipped:
            print(f"  이미 있는 {len(skipped)}일은 건너뜁니다 (--force 로 덮어쓰기)")
        if not target_dates:
            print("\n채울 날짜가 없습니다.")
            return 0

    # 한 호출이 30 영업일을 주고, 항상 end_ymd 에서 거슬러 올라간다.
    # 가장 오래된 대상일까지 닿으려면 그 사이 영업일 수 / 30 을 올림하고 여유 1 을 더한다.
    if args.depth:
        depth = args.depth
    else:
        span = sum(1 for d in index_by_date if target_dates[0] <= d <= end_ymd)
        depth = max(1, -(-span // 30) + 1)
    print(f"  종목당 호출 수 depth={depth} (커버 {depth * 30}영업일)")

    print("\n[2/4] 종목 유니버스")
    universe = load_universe(args.limit or None)
    print(f"  총 {len(universe)}종목")

    calls = depth + (0 if args.skip_market_cap else 1)
    print(f"\n[3/4] 종목별 이력 수집 (예상 {len(universe)*calls/6/60:.0f}분)")

    # 날짜별 누적 버킷
    buckets = {iso(d): {"prices": {}, "foreign_1d": {}, "inst_1d": {}, "pension_1d": {},
                        "market_cap": {}, "trade_value": {},
                        "fb": 0, "fs": 0, "ib": 0, "is_": 0}
               for d in target_dates}
    wanted = set(target_dates)

    t0 = time.monotonic()
    failed = 0
    for n, stock in enumerate(universe, 1):
        ticker = stock["ticker"]
        try:
            rows = fetch_history(kis, ticker, end_ymd, depth, cache)
        except KisError:
            failed += 1
            continue

        rows = [r for r in rows if r["stck_bsop_date"] in wanted]
        if not rows:
            continue

        shares = 0
        if not args.skip_market_cap:
            try:
                f = fetch_fundamentals(kis, ticker, end_ymd, cache)
                shares = to_int(f.get("lstn_stcn"))
            except KisError:
                shares = 0

        for r in rows:
            b = buckets[iso(r["stck_bsop_date"])]
            close = to_float(r.get("stck_clpr"))
            if close > 0:
                b["prices"][ticker] = close
                if shares > 0:
                    b["market_cap"][ticker] = int(shares * close)

            tv = to_int(r.get("acml_tr_pbmn"))
            if tv:
                b["trade_value"][ticker] = tv

            fv = float(ntby_pbmn(r, "frgn"))
            iv = float(ntby_pbmn(r, "orgn"))
            pv = float(ntby_pbmn(r, "fund"))
            if fv:
                b["foreign_1d"][ticker] = round(fv, 1)
            if iv:
                b["inst_1d"][ticker] = round(iv, 1)
            if pv:
                b["pension_1d"][ticker] = round(pv, 1)

            if fv > 0:
                b["fb"] += 1
            elif fv < 0:
                b["fs"] += 1
            if iv > 0:
                b["ib"] += 1
            elif iv < 0:
                b["is_"] += 1

        if n % 200 == 0 or n == len(universe):
            el = time.monotonic() - t0
            eta = (len(universe) - n) / (n / el) / 60 if el else 0
            print(f"  {n}/{len(universe)}  실패 {failed}  경과 {el/60:.1f}분  남은시간 ~{eta:.0f}분")

    print("\n[4/4] 스냅샷 저장")
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    for ymd in target_dates:
        d = iso(ymd)
        b = buckets[d]
        if not b["prices"]:
            print(f"  {d}: 데이터 없음 — 건너뜀")
            continue
        snapshot = {
            "date": d,
            "signals": {"buy_reversal": [], "sell_reversal": [], "leader": [], "accumulation": []},
            "prices": b["prices"],
            "foreign_1d": b["foreign_1d"],
            "inst_1d": b["inst_1d"],
            "pension_1d": b["pension_1d"],
            "breadth": {
                "foreign_buy": b["fb"], "foreign_sell": b["fs"],
                "inst_buy": b["ib"], "inst_sell": b["is_"],
            },
            "market": index_by_date.get(ymd, {}),
            "market_cap": b["market_cap"],
            "trade_value": b["trade_value"],
        }
        path = SNAP_DIR / f"{d}.json"
        path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
        written += 1
        print(f"  {d}: {len(b['prices'])}종목 ({path.stat().st_size/1024:.0f} KB)")

    files = sorted(
        (f for f in SNAP_DIR.glob("*.json") if SNAPSHOT_NAME_RE.match(f.stem)),
        key=lambda f: f.stem, reverse=True,
    )
    for old in files[MAX_SNAPSHOTS:]:
        old.unlink()

    print(f"\n{written}일 저장 완료. 총 소요 {(time.monotonic()-t0)/60:.1f}분")
    print("이어서 실행하세요: python scripts/build_timeseries.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
