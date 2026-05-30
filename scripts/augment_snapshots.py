"""
백테스트 스냅샷에 시가총액 + 거래대금 추가

기존 스냅샷: foreign_1d, inst_1d, pension_1d, prices, signals, ...
추가 필드: market_cap (시가총액 원), trade_value (거래대금 원)

목적:
- V2 시그널: 시총대비 % 정규화 (단순 절대값 임계값 탈피)
- Volume surge confirmation
- Survivorship bias 없는 historical market cap

실행:
  python scripts/augment_snapshots.py
  python scripts/augment_snapshots.py --input scripts/backtest_data/snapshots
"""

import argparse
import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from pykrx import stock  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SNAP_DIR = BASE_DIR / "scripts" / "backtest_data" / "snapshots"

SLEEP = 0.4
MAX_RETRY = 2


def fetch_market_data(yyyymmdd, market, retries=MAX_RETRY):
    """get_market_cap_by_ticker는 시가총액·거래대금 모두 반환"""
    for attempt in range(retries + 1):
        try:
            df = stock.get_market_cap_by_ticker(yyyymmdd, market=market)
            if df is None or df.empty:
                return {}, {}
            market_cap = {}
            trade_value = {}
            for ticker, row in df.iterrows():
                t = str(ticker)
                try:
                    mc = row.get("시가총액", 0)
                    tv = row.get("거래대금", 0)
                    if mc is None or tv is None:
                        continue
                    mc = int(mc)
                    tv = int(tv)
                except (KeyError, ValueError, TypeError):
                    continue
                if mc > 0:
                    market_cap[t] = mc
                if tv > 0:
                    trade_value[t] = tv
            return market_cap, trade_value
        except Exception as e:
            if attempt < retries:
                time.sleep(2)
                continue
            print(f"      [WARN] {market} 실패: {e}")
            return {}, {}
    return {}, {}


def augment_one_day(snap_path, force=False):
    """단일 스냅샷에 market_cap + trade_value 추가"""
    try:
        with open(snap_path, "r", encoding="utf-8") as f:
            snap = json.load(f)
    except Exception as e:
        return "fail", f"읽기 실패: {e}"

    # 이미 있으면 스킵
    if not force and snap.get("market_cap") and snap.get("trade_value"):
        return "skip", None

    date_str = snap.get("date") or snap_path.stem
    yyyymmdd = date_str.replace("-", "")

    market_cap = {}
    trade_value = {}

    for market in ["KOSPI", "KOSDAQ"]:
        mc, tv = fetch_market_data(yyyymmdd, market)
        market_cap.update(mc)
        trade_value.update(tv)
        time.sleep(SLEEP)

    if not market_cap and not trade_value:
        return "empty", "데이터 없음"

    if market_cap:
        snap["market_cap"] = market_cap
    if trade_value:
        snap["trade_value"] = trade_value

    # Atomic write
    tmp = snap_path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False)
    os.replace(tmp, snap_path)

    return "ok", f"mc={len(market_cap)} tv={len(trade_value)}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=str, default=None,
                        help="snapshots/ 디렉토리 (기본: scripts/backtest_data/snapshots)")
    parser.add_argument("--force", action="store_true",
                        help="이미 augment된 스냅샷도 다시 처리")
    args = parser.parse_args()

    snap_dir = Path(args.input) if args.input else DEFAULT_SNAP_DIR
    if not snap_dir.exists():
        print(f"[ERROR] {snap_dir} 없음")
        return

    # 날짜 형식 .json 파일만
    files = sorted(
        f for f in snap_dir.glob("*.json")
        if len(f.stem) == 10 and f.stem[4] == "-" and f.stem[7] == "-"
    )
    print("=" * 70)
    print(f"Augment 시작")
    print(f"  디렉토리: {snap_dir}")
    print(f"  파일: {len(files)}개")
    print(f"  Force: {args.force}")
    print("=" * 70)
    print()

    t0 = time.time()
    ok = 0
    skip = 0
    empty = 0
    fail = 0

    for i, sp in enumerate(files, 1):
        elapsed = time.time() - t0
        if i > 1 and (ok + empty + fail) > 0:
            avg = elapsed / (ok + empty + fail) if (ok + empty + fail) > 0 else 0
            remaining = (len(files) - i) * avg
            print(f"[{i:4d}/{len(files)}] {sp.stem} 처리... (경과 {int(elapsed)}s, 평균 {avg:.1f}s/일, 남은 ~{int(remaining)}s)")
        else:
            print(f"[{i:4d}/{len(files)}] {sp.stem} 처리...")

        try:
            result, msg = augment_one_day(sp, force=args.force)
        except KeyboardInterrupt:
            print("\n[중단] 사용자 인터럽트")
            break
        except Exception as e:
            print(f"      [ERROR] {e}")
            fail += 1
            continue

        if result == "ok":
            print(f"      [OK] {msg}")
            ok += 1
        elif result == "skip":
            print(f"      [SKIP] 이미 augment됨")
            skip += 1
        elif result == "empty":
            print(f"      [EMPTY] {msg}")
            empty += 1
        else:
            print(f"      [FAIL] {msg}")
            fail += 1

    total = time.time() - t0
    print()
    print("=" * 70)
    print(f"Augment 완료")
    print(f"  성공:  {ok}개")
    print(f"  스킵:  {skip}개 (이미 처리됨)")
    print(f"  비어있음: {empty}개")
    print(f"  실패:  {fail}개")
    print(f"  총 소요: {int(total)}초 ({total/60:.1f}분)")
    print("=" * 70)


if __name__ == "__main__":
    main()
