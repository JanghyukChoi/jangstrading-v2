"""
KIS Open API 로 전 종목 수급/시세/재무를 수집해 stock-rankings.json 을 만든다.

기존 파이프라인의 fetch_data.py + add_tickers.py + add_fundamentals.py +
add_price_changes.py + add_avg_cost.py + add_inst_detail.py 를 한 번에 대체한다.
KIS 의 "종목별 투자자매매동향(일별)" 이 한 호출에 30 영업일치의
외국인/기관/개인/기타 + 기관 세부 8 주체 + OHLCV 를 전부 주기 때문이다.

출력 스키마는 기존 stock-rankings.json 과 동일하다. 다운스트림
(build_timeseries / build_v3_signals / build_market_signals / build_regime /
build_rrg / generate_report / send_telegram) 은 손대지 않는다.

종목당 호출 수:
  - 수급+시세: depth 회 (기본 5 = 150 영업일. 6m(120영업일) 수익률을 내려면
               기준일 포함 121 행이 필요해서 4 회로는 모자란다)
  - 재무:      1 회 (PER/PBR/EPS/BPS/시총)
  => 전 종목 약 16,300 회, 초당 6 건 기준 약 45 분

실행:
  python scripts/kis_fetch.py                    # 전 종목
  python scripts/kis_fetch.py --limit 30         # 테스트
  python scripts/kis_fetch.py --date 20260911    # 기준일 지정
  python scripts/kis_fetch.py --no-cache         # 캐시 무시하고 새로 받기
"""

import argparse
import io
import json
import sys
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kis_api import KisClient, KisError  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "public" / "data"
CACHE_DIR = BASE_DIR / ".kis_cache"

INVESTOR_URL = "/uapi/domestic-stock/v1/quotations/investor-trade-by-stock-daily"
INVESTOR_TR = "FHPTJ04160001"
PRICE_URL = "/uapi/domestic-stock/v1/quotations/inquire-price"
PRICE_TR = "FHKST01010100"

MASTER = {
    "KOSPI": ("https://new.real.download.dws.co.kr/common/master/kospi_code.mst.zip", 228),
    "KOSDAQ": ("https://new.real.download.dws.co.kr/common/master/kosdaq_code.mst.zip", 222),
}

# 기존 fetch_data.py 와 동일한 정의 (영업일 수)
PERIODS = {"1d": 1, "1w": 5, "1m": 20, "3m": 60, "6m": 120}

# 한 호출이 돌려주는 영업일 수 (실측)
ROWS_PER_CALL = 30

# 기관 세부 주체: 출력 라벨 -> KIS 순매수 수량/대금 필드 접두사
INST_DETAIL = {
    "금융투자": "scrt",
    "보험": "insu",
    "투신": "ivtr",
    "사모": "pe_fund",
    "은행": "bank",
    "연기금": "fund",
}

# 평균단가 계산 기간 (영업일)
AVG_COST_LOOKBACK = 120


def to_int(v):
    """KIS 는 정수 필드도 "6564.00" 처럼 소수 문자열로 주는 경우가 있다."""
    try:
        return int(float(str(v).strip() or 0))
    except (TypeError, ValueError):
        return 0


def to_float(v):
    try:
        return float(str(v).strip() or 0)
    except (TypeError, ValueError):
        return 0.0


def ntby_pbmn(row, prefix):
    """주체별 순매수 '대금'(백만원). KIS 는 접미사가 주체마다 다르다."""
    for suffix in ("_ntby_tr_pbmn", "_ntby_pbmn"):
        key = prefix + suffix
        if key in row:
            return to_int(row[key])
    return 0


def ntby_qty(row, prefix):
    """주체별 순매수 '수량'. 접미사가 _ntby_qty 인 것과 _ntby_vol 인 것이 섞여 있다."""
    for suffix in ("_ntby_qty", "_ntby_vol"):
        key = prefix + suffix
        if key in row:
            return to_int(row[key])
    return 0


# ─── 종목 유니버스 ──────────────────────────────────────────────────
def load_universe(limit=None):
    """KIS 종목 마스터에서 (ticker, name, market) 목록. 인증 불필요."""
    universe = []
    for market, (url, tail) in MASTER.items():
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        z = zipfile.ZipFile(io.BytesIO(resp.content))
        raw = z.read(z.namelist()[0]).decode("cp949", errors="replace")

        count = 0
        for line in raw.splitlines():
            if not line.strip():
                continue
            head = line[: len(line) - tail]
            rest = line[len(line) - tail :]
            code = head[0:9].rstrip()
            name = head[21:].strip()
            # rest[1:3] == "ST" 가 주권. ETF/ETN/리츠/펀드는 제외.
            if rest[1:3] != "ST" or len(code) != 6:
                continue
            universe.append({"ticker": code, "name": name, "market": market})
            count += 1
        print(f"  {market}: {count}종목")

    universe.sort(key=lambda x: x["ticker"])
    if limit:
        universe = universe[:limit]
    return universe


# ─── 수집 ───────────────────────────────────────────────────────────
def fetch_history(kis, ticker, end_date, depth, cache=True):
    """종목의 일별 투자자매매동향 + OHLCV 를 depth 회 거슬러 올라가며 모은다.

    Returns: 날짜 오름차순 row 리스트
    """
    cache_file = CACHE_DIR / f"{ticker}_{end_date}_{depth}.json"
    if cache and cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except ValueError:
            pass

    seen = {}
    cursor = end_date
    for _ in range(depth):
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
        # 종가가 비어 있으면 실제로 거래된 종목이 아니다 (없는 코드 등)
        rows = [r for r in rows if str(r.get("stck_clpr", "")).strip()]
        if not rows:
            break

        for r in rows:
            seen[r["stck_bsop_date"]] = r

        oldest = min(r["stck_bsop_date"] for r in rows)
        cursor = (datetime.strptime(oldest, "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d")

    out = [seen[d] for d in sorted(seen)]
    if cache and out:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def fetch_fundamentals(kis, ticker, end_date, cache=True):
    """PER/PBR/EPS/BPS/시가총액. inquire-price 는 '현재' 기준이라 장 마감 후 호출."""
    cache_file = CACHE_DIR / f"fund_{ticker}_{end_date}.json"
    if cache and cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except ValueError:
            pass

    body = kis.get(
        PRICE_URL,
        tr_id=PRICE_TR,
        params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker},
    )
    out = body.get("output") or {}
    if cache and out:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


# ─── 집계 ───────────────────────────────────────────────────────────
def aggregate_flows(rows):
    """기간별 외국인/기관/합계 순매수 대금(백만원) 과 기관 세부주체."""
    foreign, institution, combined = {}, {}, {}
    inst_detail, pension = {}, {}

    for period, n in PERIODS.items():
        window = rows[-n:] if n <= len(rows) else rows
        f = sum(ntby_pbmn(r, "frgn") for r in window)
        i = sum(ntby_pbmn(r, "orgn") for r in window)
        foreign[period] = float(f)
        institution[period] = float(i)
        combined[period] = float(f + i)

        detail = {}
        for label, prefix in INST_DETAIL.items():
            detail[label] = float(sum(ntby_pbmn(r, prefix) for r in window))
        inst_detail[period] = detail
        pension[period] = detail["연기금"]

    return foreign, institution, combined, inst_detail, pension


def aggregate_price_changes(rows):
    """기간별 수익률(%). 기준일 종가 대비 n 영업일 전 종가."""
    if not rows:
        return {p: None for p in PERIODS}
    last = to_float(rows[-1].get("stck_clpr"))
    out = {}
    for period, n in PERIODS.items():
        idx = len(rows) - 1 - n
        if last <= 0 or idx < 0:
            out[period] = None
            continue
        base = to_float(rows[idx].get("stck_clpr"))
        out[period] = round((last - base) / base * 100, 2) if base > 0 else None
    return out


def calc_avg_cost(rows, prefix):
    """이동평균 원가법 추정 평균단가. add_avg_cost.py 와 동일한 알고리즘."""
    avg_cost = 0.0
    position = 0

    for r in rows[-AVG_COST_LOOKBACK:]:
        vol = to_int(r.get("acml_vol"))
        amount = to_int(r.get("acml_tr_pbmn"))  # 원 단위
        vwap = (amount / vol) if vol > 0 else 0
        if vwap <= 0:
            continue

        net_vol = ntby_qty(r, prefix)
        if net_vol > 0:
            total = avg_cost * position + vwap * net_vol
            position += net_vol
            if position > 0:
                avg_cost = total / position
        elif net_vol < 0:
            position += net_vol
            if position <= 0:
                avg_cost = 0.0
                position = 0

    if position <= 0 or avg_cost <= 0:
        return None
    return round(avg_cost, 0)


def build_avg_cost(rows):
    if not rows:
        return None
    price = to_float(rows[-1].get("stck_clpr"))
    if price <= 0:
        return None

    out = {"price": price}
    for label, prefix in (("foreign", "frgn"), ("institution", "orgn")):
        cost = calc_avg_cost(rows, prefix)
        if cost:
            out[label] = {
                "avg_cost": int(cost),
                "pnl_pct": round((price - cost) / cost * 100, 2),
            }
    return out if len(out) > 1 else None


# ─── 메인 ───────────────────────────────────────────────────────────
def latest_business_day(kis):
    """KOSPI 지수가 조회되는 가장 최근 날짜를 기준일로 삼는다."""
    today = datetime.today().date()
    for _ in range(12):
        if today.weekday() >= 5:
            today -= timedelta(days=1)
            continue
        ymd = today.strftime("%Y%m%d")
        body = kis.get(
            "/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice",
            tr_id="FHKUP03500100",
            params={
                "FID_COND_MRKT_DIV_CODE": "U",
                "FID_INPUT_ISCD": "0001",
                "FID_INPUT_DATE_1": ymd,
                "FID_INPUT_DATE_2": ymd,
                "FID_PERIOD_DIV_CODE": "D",
            },
        )
        rows = body.get("output2") or []
        if isinstance(rows, dict):
            rows = [rows]
        rows = [r for r in rows if str(r.get("bstp_nmix_prpr", "")).strip()]
        if rows and rows[0].get("stck_bsop_date") == ymd:
            return ymd
        today -= timedelta(days=1)
    raise SystemExit("최근 영업일을 찾지 못했습니다.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="", help="기준일 YYYYMMDD (기본: 최근 영업일)")
    ap.add_argument("--depth", type=int, default=5,
                    help=f"종목당 수급 조회 횟수 (1회={ROWS_PER_CALL}영업일, 기본 5=150일). "
                         "6m(120영업일) 수익률은 기준일 포함 121행이 필요해 4로는 모자란다")
    ap.add_argument("--limit", type=int, default=0, help="상위 N 종목만 (테스트용)")
    ap.add_argument("--no-cache", action="store_true", help="캐시 무시")
    ap.add_argument("--skip-fundamentals", action="store_true",
                    help="PER/PBR/시총 조회 생략 (호출 절반 절약)")
    args = ap.parse_args()

    cache = not args.no_cache
    kis = KisClient()

    date_str = args.date or latest_business_day(kis)
    date_iso = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    print("=" * 60)
    print(f"KIS 전 종목 수집  기준일={date_iso}  depth={args.depth}")
    print("=" * 60)

    print("\n[1/3] 종목 유니버스 로드")
    universe = load_universe(args.limit or None)
    print(f"  총 {len(universe)}종목")

    print(f"\n[2/3] 종목별 수급/시세 수집 (예상 {len(universe) * (args.depth + (0 if args.skip_fundamentals else 1)) / 6 / 60:.0f}분)")
    results = []
    failed = []
    t0 = time.monotonic()

    for n, stock in enumerate(universe, 1):
        ticker = stock["ticker"]
        try:
            rows = fetch_history(kis, ticker, date_str, args.depth, cache)
        except KisError as e:
            failed.append((ticker, str(e)))
            continue

        if not rows or rows[-1]["stck_bsop_date"] != date_str:
            # 기준일 데이터가 없으면 거래정지/상장폐지 등. 건너뛴다.
            continue

        foreign, institution, combined, inst_detail, pension = aggregate_flows(rows)
        item = {
            "name": stock["name"],
            "market": stock["market"],
            "foreign": foreign,
            "institution": institution,
            "combined": combined,
            "ticker": ticker,
            "price_change": aggregate_price_changes(rows),
            "inst_detail": inst_detail,
            "pension": pension,
        }

        avg = build_avg_cost(rows)
        if avg:
            item["avg_cost"] = avg

        # 스냅샷용 원시값
        last = rows[-1]
        item["_close"] = to_float(last.get("stck_clpr"))
        item["_trade_value"] = to_int(last.get("acml_tr_pbmn"))
        item["_foreign_1d"] = float(ntby_pbmn(last, "frgn"))
        item["_inst_1d"] = float(ntby_pbmn(last, "orgn"))
        item["_pension_1d"] = float(ntby_pbmn(last, "fund"))

        if not args.skip_fundamentals:
            try:
                f = fetch_fundamentals(kis, ticker, date_str, cache)
                item["per"] = to_float(f.get("per")) or None
                item["pbr"] = to_float(f.get("pbr")) or None
                item["eps"] = to_int(f.get("eps")) or None
                item["bps"] = to_int(f.get("bps")) or None
                # hts_avls 는 억원 단위 — 기존 스키마와 동일
                item["market_cap"] = to_float(f.get("hts_avls")) or None
                # KIS 현재가 시세에는 배당수익률이 없다. 프론트가 null 을 처리한다.
                item["div_yield"] = None
            except KisError as e:
                failed.append((ticker, f"fundamentals: {e}"))

        results.append(item)

        if n % 100 == 0 or n == len(universe):
            el = time.monotonic() - t0
            rate = n / el if el else 0
            eta = (len(universe) - n) / rate / 60 if rate else 0
            print(f"  {n}/{len(universe)}  수집 {len(results)}  실패 {len(failed)}  "
                  f"경과 {el/60:.1f}분  남은시간 ~{eta:.0f}분")

    print(f"\n[3/3] 저장")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    payload = {
        "date": date_iso,
        "unit": "백만원",
        "count": len(results),
        "data": results,
    }
    out_path = DATA_DIR / "stock-rankings.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"  stock-rankings.json ({out_path.stat().st_size/1024:.1f} KB, {len(results)}종목)")

    meta_path = DATA_DIR / "meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "date": date_iso,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
                "count": len(results),
                "source": "KIS Open API",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print("  meta.json")

    if failed:
        print(f"\n  실패 {len(failed)}건 (상위 5건):")
        for t, e in failed[:5]:
            print(f"    {t}: {e[:90]}")

    print(f"\n총 소요 {(time.monotonic()-t0)/60:.1f}분")
    return 0


if __name__ == "__main__":
    sys.exit(main())
