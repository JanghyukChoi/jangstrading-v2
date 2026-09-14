"""
KIS API 사전 검증 스크립트

앱키를 받은 직후 한 번 돌려서, 본 마이그레이션이 기대는 가정들이 실제로
맞는지 확인한다. 여기서 다 통과해야 나머지 스크립트를 옮길 수 있다.

확인 항목:
  1. 토큰 발급이 되는가
  2. 종목별 투자자매매동향(일별) 이 외국인/기관/기관 세부주체 + OHLCV 를
     한 번에 주는가, 한 호출에 며칠치가 오는가
  3. 기간별시세가 PER/PBR/EPS/BPS/시가총액을 주는가
  4. 현재가 시세가 종목명/시총/PER/PBR 을 주는가
  5. 업종 일자별지수(KOSPI) 가 오는가
  6. 종목 마스터 파일(인증 불필요)에서 전 종목 코드/이름이 나오는가

실행:
    python scripts/kis_probe.py
    python scripts/kis_probe.py --ticker 000660 --date 20260911
"""

import argparse
import io
import sys
import zipfile
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from kis_api import KisClient, KisError  # noqa: E402

MASTER_URLS = {
    "KOSPI": ("https://new.real.download.dws.co.kr/common/master/kospi_code.mst.zip", 228),
    "KOSDAQ": ("https://new.real.download.dws.co.kr/common/master/kosdaq_code.mst.zip", 222),
}

# 종목별 투자자매매동향에서 우리가 실제로 쓰려는 필드
WANTED_INVESTOR_FIELDS = [
    ("stck_bsop_date", "영업일자"),
    ("stck_clpr", "종가"),
    ("stck_oprc", "시가"),
    ("stck_hgpr", "고가"),
    ("stck_lwpr", "저가"),
    ("acml_vol", "누적거래량"),
    ("acml_tr_pbmn", "누적거래대금"),
    ("frgn_ntby_qty", "외국인 순매수 수량"),
    ("frgn_ntby_tr_pbmn", "외국인 순매수 대금"),
    ("orgn_ntby_qty", "기관계 순매수 수량"),
    ("orgn_ntby_tr_pbmn", "기관계 순매수 대금"),
    ("prsn_ntby_qty", "개인 순매수 수량"),
    ("scrt_ntby_qty", "금융투자(증권) 순매수"),
    ("insu_ntby_qty", "보험 순매수"),
    ("ivtr_ntby_qty", "투신 순매수"),
    ("pe_fund_ntby_vol", "사모 순매수"),
    ("bank_ntby_qty", "은행 순매수"),
    ("fund_ntby_qty", "연기금 순매수"),
]

# 기간별시세 output1 에는 BPS 가 없다(확인함). BPS 는 현재가 시세에서 받는다.
WANTED_FUNDAMENTAL_FIELDS = [
    ("per", "PER"),
    ("pbr", "PBR"),
    ("eps", "EPS"),
    ("hts_avls", "시가총액"),
    ("lstn_stcn", "상장주수"),
    ("hts_kor_isnm", "종목명"),
]

results = []


def check(name, ok, detail=""):
    mark = "OK  " if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail else ""))
    results.append((name, ok))
    return ok


def report_fields(sample, wanted):
    missing = []
    for key, label in wanted:
        if key in sample:
            print(f"        {key:22s} {label:22s} = {sample[key]!r}")
        else:
            missing.append(f"{key}({label})")
    return missing


def probe_investor_daily(kis, ticker, date):
    print("\n[2] 종목별 투자자매매동향(일별)  FHPTJ04160001")
    try:
        body = kis.get(
            "/uapi/domestic-stock/v1/quotations/investor-trade-by-stock-daily",
            tr_id="FHPTJ04160001",
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": ticker,
                "FID_INPUT_DATE_1": date,
                "FID_ORG_ADJ_PRC": "",
                "FID_ETC_CLS_CODE": "",
            },
        )
    except KisError as e:
        return check("투자자매매동향 호출", False, str(e))

    out1 = body.get("output1")
    out2 = body.get("output2") or []
    if isinstance(out2, dict):
        out2 = [out2]

    check("투자자매매동향 호출", True, f"output1={'있음' if out1 else '없음'}, output2={len(out2)}행")
    if not out2:
        print("        output2 가 비어 있음 — 날짜(휴장일?) 확인 필요")
        print(f"        응답 키: {[k for k in body if not k.startswith('_')]}")
        return False

    rows = sorted(out2, key=lambda r: r.get("stck_bsop_date", ""))
    print(f"        한 호출 커버 기간: {rows[0].get('stck_bsop_date')} ~ {rows[-1].get('stck_bsop_date')} ({len(rows)}일)")
    print(f"        연속조회 tr_cont 응답: {body.get('_tr_cont')!r}")
    print("        --- 최근일 필드 ---")
    missing = report_fields(rows[-1], WANTED_INVESTOR_FIELDS)
    return check(
        "투자자매매동향 필수 필드",
        not missing,
        "누락: " + ", ".join(missing) if missing else "전부 존재",
    )


def probe_item_chart(kis, ticker, date):
    print("\n[3] 국내주식 기간별시세(일)  FHKST03010100")
    try:
        body = kis.get(
            "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
            tr_id="FHKST03010100",
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": ticker,
                "FID_INPUT_DATE_1": date,
                "FID_INPUT_DATE_2": date,
                "FID_PERIOD_DIV_CODE": "D",
                "FID_ORG_ADJ_PRC": "0",
            },
        )
    except KisError as e:
        return check("기간별시세 호출", False, str(e))

    out1 = body.get("output1") or {}
    out2 = body.get("output2") or []
    if isinstance(out2, dict):
        out2 = [out2]
    check("기간별시세 호출", True, f"output2={len(out2)}행")
    print("        --- output1 (종목 요약) ---")
    missing = report_fields(out1, WANTED_FUNDAMENTAL_FIELDS)
    if out2:
        print(f"        --- output2 최근일: {out2[0].get('stck_bsop_date')} 종가={out2[0].get('stck_clpr')} ---")
    return check(
        "기간별시세 재무 필드",
        not missing,
        "누락: " + ", ".join(missing) if missing else "전부 존재",
    )


def probe_price(kis, ticker):
    print("\n[4] 주식현재가 시세  FHKST01010100")
    try:
        body = kis.get(
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            tr_id="FHKST01010100",
            params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker},
        )
    except KisError as e:
        return check("현재가 시세 호출", False, str(e))

    out = body.get("output") or {}
    check("현재가 시세 호출", True)
    missing = report_fields(
        out,
        [
            ("stck_prpr", "현재가"),
            ("per", "PER"),
            ("pbr", "PBR"),
            ("eps", "EPS"),
            ("bps", "BPS"),
            ("hts_avls", "시가총액"),
            ("lstn_stcn", "상장주수"),
            ("acml_tr_pbmn", "누적거래대금"),
            ("bstp_kor_isnm", "업종명"),
        ],
    )
    return check(
        "현재가 재무 필드",
        not missing,
        "누락: " + ", ".join(missing) if missing else "전부 존재",
    )


def probe_index(kis, date):
    print("\n[5] 업종 일자별지수 (KOSPI)  FHKUP03500100")
    try:
        body = kis.get(
            "/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice",
            tr_id="FHKUP03500100",
            params={
                "FID_COND_MRKT_DIV_CODE": "U",
                "FID_INPUT_ISCD": "0001",  # 0001: KOSPI 종합
                "FID_INPUT_DATE_1": date,
                "FID_INPUT_DATE_2": date,
                "FID_PERIOD_DIV_CODE": "D",
            },
        )
    except KisError as e:
        return check("KOSPI 지수 호출", False, str(e))

    out2 = body.get("output2") or []
    if isinstance(out2, dict):
        out2 = [out2]
    if not out2:
        return check("KOSPI 지수 호출", False, "output2 비어 있음")
    r = out2[0]
    return check(
        "KOSPI 지수 호출",
        True,
        f"{r.get('stck_bsop_date')} 종가={r.get('bstp_nmix_prpr')}",
    )


def probe_master():
    print("\n[6] 종목 마스터 파일 (인증 불필요)")
    ok_all = True
    for market, (url, tail) in MASTER_URLS.items():
        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            z = zipfile.ZipFile(io.BytesIO(resp.content))
            raw = z.read(z.namelist()[0]).decode("cp949", errors="replace")
        except Exception as e:
            ok_all &= check(f"{market} 마스터 다운로드", False, repr(e))
            continue

        stocks = []
        for line in raw.splitlines():
            if not line.strip():
                continue
            head = line[: len(line) - tail]
            rest = line[len(line) - tail :]
            code = head[0:9].rstrip()
            name = head[21:].strip()
            group = rest[1:3]
            if group == "ST" and len(code) == 6:
                stocks.append((code, name))

        ok_all &= check(
            f"{market} 주권 추출", len(stocks) > 500, f"{len(stocks)}종목"
        )
        if stocks:
            print(f"        예: {stocks[:3]}")
    return ok_all


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", default="005930", help="검증에 쓸 종목코드")
    ap.add_argument("--date", default="", help="기준일 YYYYMMDD (기본: 오늘)")
    args = ap.parse_args()

    from datetime import datetime

    date = args.date or datetime.today().strftime("%Y%m%d")

    print("=" * 64)
    print(f"KIS API 사전 검증  (종목={args.ticker}, 기준일={date})")
    print("=" * 64)

    print("\n[1] 토큰 발급")
    try:
        kis = KisClient()
        token = kis.token
        check("토큰 발급", bool(token), f"길이 {len(token)}")
    except SystemExit as e:
        print(e)
        return 1
    except KisError as e:
        check("토큰 발급", False, str(e))
        return 1

    probe_investor_daily(kis, args.ticker, date)
    probe_item_chart(kis, args.ticker, date)
    probe_price(kis, args.ticker)
    probe_index(kis, date)
    probe_master()

    print("\n" + "=" * 64)
    failed = [n for n, ok in results if not ok]
    if failed:
        print(f"실패 {len(failed)}건:")
        for n in failed:
            print(f"  - {n}")
        print("\n이 항목들을 해결해야 마이그레이션을 진행할 수 있습니다.")
        return 1
    print(f"전체 통과 ({len(results)}건). 마이그레이션 진행 가능.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
