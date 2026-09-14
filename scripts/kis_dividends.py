"""
종목별 최근 12 개월 배당을 모아 dividends.json 을 만든다.

KIS 현재가 시세에는 배당수익률이 없어서, 예탁원정보(배당일정)에서 주당배당금을
받아 kis_fetch.py 가 종가로 나눠 배당수익률을 계산한다.

벌크 조회(SHT_CD 공백)는 쓸 수 없다. 응답에 CTS 가 없고 record_date 역순으로
100 건씩만 오는데, 결산배당은 record_date 가 12/31 에 수천 종목 몰려서 그 날짜를
다 못 받고 넘어가게 된다. 그래서 종목별로 1 회씩 조회한다(약 2,700 회, 7~8 분).

배당은 분기에 한 번 바뀌는 값이라 매일 돌릴 필요가 없다. --max-age-days 안에
갱신된 파일이 있으면 아무것도 하지 않고 끝난다.

실행:
  python scripts/kis_dividends.py                    # 7일 넘었으면 갱신
  python scripts/kis_dividends.py --force            # 무조건 갱신
  python scripts/kis_dividends.py --max-age-days 30
"""

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kis_api import KisClient, KisError  # noqa: E402
from kis_fetch import DATA_DIR, load_universe, to_float  # noqa: E402

DIVIDEND_URL = "/uapi/domestic-stock/v1/ksdinfo/dividend"
DIVIDEND_TR = "HHKDB669102C0"
OUT_PATH = DATA_DIR / "dividends.json"


def fetch_dividend(kis, ticker, f_dt, t_dt):
    """최근 12 개월 배당을 '액면가 1 원당 배당액'으로 환산해 합산한다.

    주당배당금을 그대로 합치면 안 된다. 기간 중 액면분할이 있었으면 배당 기록은
    분할 전 주식 기준이라, 분할 후 주가로 나누는 순간 수익률이 분할 배수만큼
    부풀려진다. (실측: 대한제분 5000->500 분할로 3.45% 가 34.54% 로 나왔다)

    그래서 각 기록을 그 시점 액면가로 나눠 저장하고, 쓰는 쪽에서 현재 액면가를
    곱해 현재 주식 기준 주당배당금으로 되돌린다.
    """
    body = kis.get(
        DIVIDEND_URL,
        tr_id=DIVIDEND_TR,
        params={
            "CTS": " ",
            "GB1": "0",  # 배당 전체
            "F_DT": f_dt,
            "T_DT": t_dt,
            "SHT_CD": ticker,
            "HIGH_GB": " ",
        },
    )
    rows = body.get("output1") or []
    if isinstance(rows, dict):
        rows = [rows]

    # per_sto_divi_amt 가 주당 현금배당금. 주식배당(stk_divi_rate)은 제외한다.
    total = 0.0
    for r in rows:
        amount = to_float(r.get("per_sto_divi_amt"))
        face = to_float(r.get("face_val"))
        if amount > 0 and face > 0:
            total += amount / face
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-age-days", type=int, default=7,
                    help="이 일수 안에 갱신됐으면 건너뛴다 (기본 7)")
    ap.add_argument("--force", action="store_true", help="신선도 무시하고 갱신")
    ap.add_argument("--limit", type=int, default=0, help="상위 N 종목만 (테스트용)")
    args = ap.parse_args()

    if not args.force and OUT_PATH.exists():
        try:
            prev = json.loads(OUT_PATH.read_text(encoding="utf-8"))
            updated = datetime.fromisoformat(prev.get("updated_at", ""))
            age = (datetime.now() - updated).days
            if age < args.max_age_days:
                print(f"dividends.json 이 {age}일 전 갱신본입니다 "
                      f"(기준 {args.max_age_days}일). 건너뜁니다.")
                return 0
        except (ValueError, TypeError):
            pass

    kis = KisClient()
    today = datetime.today()
    t_dt = today.strftime("%Y%m%d")
    f_dt = (today - timedelta(days=365)).strftime("%Y%m%d")

    print("=" * 60)
    print(f"배당 수집  {f_dt} ~ {t_dt}")
    print("=" * 60)

    universe = load_universe(args.limit or None)
    print(f"  총 {len(universe)}종목\n")

    dividends = {}
    failed = 0
    t0 = time.monotonic()

    for n, stock in enumerate(universe, 1):
        ticker = stock["ticker"]
        try:
            amount = fetch_dividend(kis, ticker, f_dt, t_dt)
        except KisError:
            failed += 1
            continue
        if amount > 0:
            dividends[ticker] = round(amount, 6)

        if n % 300 == 0 or n == len(universe):
            el = time.monotonic() - t0
            eta = (len(universe) - n) / (n / el) / 60 if el else 0
            print(f"  {n}/{len(universe)}  배당 있음 {len(dividends)}  실패 {failed}  "
                  f"경과 {el/60:.1f}분  남은시간 ~{eta:.0f}분")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(
            {
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "period": {"from": f_dt, "to": t_dt},
                "unit": "액면가 1원당 배당액 (12개월 합계). 주당배당금 = 이 값 x 현재 액면가",
                "data": dividends,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\ndividends.json 저장 ({len(dividends)}종목, "
          f"{OUT_PATH.stat().st_size/1024:.0f} KB, {(time.monotonic()-t0)/60:.1f}분)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
