"""
KRX 과거 일별 종목 순매수 데이터 백필

목적: 종목 상세 페이지의 외국인/기관 누적 순매수 라인 차트를 위해
      과거 영업일별 종목별 순매수 데이터를 snapshots/ 폴더에 채움.

저장: public/data/snapshots/{YYYY-MM-DD}.json
필드: foreign_1d, inst_1d, pension_1d, prices (기존 파일 있으면 병합)

사용 예:
  python scripts/backfill_snapshots.py --days 5             # 최근 5 영업일
  python scripts/backfill_snapshots.py --days 252           # 약 1년
  python scripts/backfill_snapshots.py --end 2026-05-22 --days 30  # 특정일 기준
  python scripts/backfill_snapshots.py --days 5 --force     # 기존 파일 덮어쓰기

주의:
- pykrx는 KRX 서버 호출이라 rate limit 위험. 호출 간 0.4초 sleep.
- 1년치 백필 시 30~50분 소요.
"""

import argparse
import json
import time
import sys
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

# pykrx는 import 시점에 KRX 로그인을 시도하므로 dotenv를 먼저 로드해야 함
load_dotenv()

from pykrx import stock  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "public" / "data"
# 기본 출력 경로 (--output으로 override 가능)
DEFAULT_SNAP_DIR = DATA_DIR / "snapshots"

MARKETS = ["KOSPI", "KOSDAQ"]
UNIT = 1_000_000  # 백만원

# 호출 간 sleep (rate limit 회피)
SLEEP = 0.4
# 실패 시 재시도 횟수
MAX_RETRY = 2


def get_business_days(end_date, count):
    """end_date 이전(포함) 영업일 목록 반환"""
    # 충분히 넉넉하게 가져온 뒤 마지막 count개만 사용
    start = end_date - timedelta(days=count * 2 + 30)
    df = stock.get_market_ohlcv(
        start.strftime("%Y%m%d"),
        end_date.strftime("%Y%m%d"),
        "005930",
    )
    days = sorted(df.index.tolist())
    if len(days) > count:
        return days[-count:]
    return days


def fetch_investor_flows(date_str, market, investor):
    """특정 일자/시장/투자자의 종목별 순매수 (단위: 백만원)
    반환: {ticker: amount} dict, 0이 아닌 값만"""
    result = {}
    for attempt in range(MAX_RETRY + 1):
        try:
            df = stock.get_market_net_purchases_of_equities(
                date_str, date_str, market, investor
            )
            if df is None or df.empty:
                return result
            # index는 보통 ticker 코드
            for ticker, row in df.iterrows():
                amount_won = row.get("순매수거래대금", 0)
                if amount_won == 0:
                    continue
                amount = round(amount_won / UNIT, 1)
                if amount != 0:
                    result[str(ticker)] = amount
            return result
        except Exception as e:
            if attempt < MAX_RETRY:
                time.sleep(2)
                continue
            print(f"      [WARN] {market}/{investor} 실패 (재시도 소진): {e}")
            return result
    return result


def fetch_prices(date_str, market):
    """시장 전체 종목 종가 반환: {ticker: price}"""
    result = {}
    for attempt in range(MAX_RETRY + 1):
        try:
            df = stock.get_market_ohlcv_by_ticker(date_str, market=market)
            if df is None or df.empty:
                return result
            for ticker, row in df.iterrows():
                close = row.get("종가", 0)
                if close:
                    result[str(ticker)] = float(close)
            return result
        except Exception as e:
            if attempt < MAX_RETRY:
                time.sleep(2)
                continue
            print(f"      [WARN] {market} 종가 실패: {e}")
            return result
    return result


def fetch_one_day(date_obj):
    """하루 영업일의 외국인/기관/연기금 순매수 + 종가 전체 수집"""
    date_str = date_obj.strftime("%Y%m%d")

    foreign_1d = {}
    inst_1d = {}
    pension_1d = {}
    prices = {}

    for market in MARKETS:
        # 외국인
        flows = fetch_investor_flows(date_str, market, "외국인")
        foreign_1d.update(flows)
        time.sleep(SLEEP)

        # 기관합계
        flows = fetch_investor_flows(date_str, market, "기관합계")
        inst_1d.update(flows)
        time.sleep(SLEEP)

        # 연기금
        flows = fetch_investor_flows(date_str, market, "연기금")
        pension_1d.update(flows)
        time.sleep(SLEEP)

        # 종가
        p = fetch_prices(date_str, market)
        prices.update(p)
        time.sleep(SLEEP)

    return foreign_1d, inst_1d, pension_1d, prices


def merge_snapshot(snap_dir, date_str, foreign_1d, inst_1d, pension_1d, prices, force=False):
    """기존 스냅샷에 백필 데이터 병합 (없으면 신규 생성). Atomic write."""
    snap_path = snap_dir / f"{date_str}.json"
    if snap_path.exists():
        try:
            with open(snap_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {"date": date_str}
    else:
        data = {"date": date_str}

    # 일별 수급은 항상 갱신 (백필 우선)
    if foreign_1d or force:
        data["foreign_1d"] = foreign_1d
    if inst_1d or force:
        data["inst_1d"] = inst_1d
    if pension_1d or force:
        data["pension_1d"] = pension_1d
    # 종가는 기존 없을 때만 채움 (기존 저장본이 더 신뢰성 있음)
    if prices and (not data.get("prices") or force):
        data["prices"] = prices

    # 백필 불가능한 필드는 기본값 보장
    data.setdefault(
        "signals",
        {"buy_reversal": [], "sell_reversal": [], "divergence": [], "accumulation": []},
    )
    data.setdefault("breadth", {})
    data.setdefault("market", {})

    # Atomic write: tmp 파일에 쓴 뒤 rename (충돌 시 부분 파일 안 남김)
    tmp_path = snap_path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    import os
    os.replace(tmp_path, snap_path)

    return snap_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=None, help="최근 영업일 수 (기본 252 = ~1년)")
    parser.add_argument("--years", type=int, default=None, help="N년치 (--days보다 우선, N*252 영업일)")
    parser.add_argument("--end", type=str, default=None, help="기준일 YYYY-MM-DD (기본: 오늘)")
    parser.add_argument("--output", type=str, default=None, help="저장 디렉토리 (기본 public/data/snapshots)")
    parser.add_argument("--force", action="store_true", help="기존 일별 수급 데이터도 덮어쓰기")
    parser.add_argument("--skip-existing", action="store_true", help="이미 일별 수급 있는 날 건너뛰기 (기본 동작)")
    args = parser.parse_args()

    # 영업일 수 결정: years > days > 기본값
    if args.years:
        target_days = args.years * 252
    elif args.days:
        target_days = args.days
    else:
        target_days = 252

    end_date = (
        datetime.strptime(args.end, "%Y-%m-%d").date() if args.end else datetime.now().date()
    )

    # 출력 디렉토리
    snap_dir = Path(args.output) / "snapshots" if args.output else DEFAULT_SNAP_DIR
    snap_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print(f"백필 시작")
    print(f"  기준일: {end_date}")
    print(f"  영업일 수: {target_days}" + (f" ({args.years}년)" if args.years else ""))
    print(f"  저장 위치: {snap_dir}")
    print(f"  기존 데이터 처리: {'덮어쓰기' if args.force else '병합 (있으면 스킵)'}")
    print("=" * 70)

    print("\n영업일 목록 수집 중...")
    biz_days = get_business_days(end_date, target_days)
    print(f"  실제 수집할 영업일: {len(biz_days)}일")
    print(f"  범위: {biz_days[0].strftime('%Y-%m-%d')} ~ {biz_days[-1].strftime('%Y-%m-%d')}")
    print()

    t0 = time.time()
    success = 0
    skipped = 0
    failed = 0

    for i, day in enumerate(biz_days, 1):
        date_str = day.strftime("%Y-%m-%d")
        snap_path = snap_dir / f"{date_str}.json"

        # 이미 일별 수급 있으면 스킵 (force가 아니면)
        if not args.force and snap_path.exists():
            try:
                with open(snap_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                if existing.get("foreign_1d") or existing.get("inst_1d"):
                    print(f"[{i:3d}/{len(biz_days)}] {date_str} → 이미 수급 데이터 있음, 스킵")
                    skipped += 1
                    continue
            except Exception:
                pass

        elapsed = time.time() - t0
        if i > 1 and success > 0:
            avg_per_day = elapsed / (i - 1 - skipped) if (i - 1 - skipped) > 0 else 0
            remaining = avg_per_day * (len(biz_days) - i)
            print(
                f"[{i:3d}/{len(biz_days)}] {date_str} 수집 중... "
                f"(경과 {int(elapsed)}s, 평균 {avg_per_day:.1f}s/일, 남은 시간 ~{int(remaining)}s)"
            )
        else:
            print(f"[{i:3d}/{len(biz_days)}] {date_str} 수집 중...")

        try:
            foreign_1d, inst_1d, pension_1d, prices = fetch_one_day(day)
            if not foreign_1d and not inst_1d:
                print(f"      [WARN] 데이터 비어있음, 건너뜀")
                failed += 1
                continue

            saved = merge_snapshot(
                snap_dir, date_str, foreign_1d, inst_1d, pension_1d, prices, force=args.force
            )
            size_kb = saved.stat().st_size / 1024
            print(
                f"      [OK] 외국인 {len(foreign_1d):4d} / 기관 {len(inst_1d):4d} / "
                f"연기금 {len(pension_1d):4d} / 종가 {len(prices):4d} ({size_kb:.1f}KB)"
            )
            success += 1
        except KeyboardInterrupt:
            print("\n[중단] 사용자 인터럽트")
            sys.exit(1)
        except Exception as e:
            print(f"      [ERROR] {e}")
            failed += 1

    total = time.time() - t0
    print()
    print("=" * 70)
    print("백필 완료")
    print(f"  성공: {success}일")
    print(f"  스킵: {skipped}일 (이미 수급 데이터 있음)")
    print(f"  실패: {failed}일")
    print(f"  총 소요: {int(total)}초 ({total / 60:.1f}분)")
    print("=" * 70)


if __name__ == "__main__":
    main()
