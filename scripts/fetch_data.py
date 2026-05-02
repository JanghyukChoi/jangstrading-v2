"""
Jangstrading v2 — 일일 배치 스크립트
pykrx로 외국인/기관 수급 데이터를 수집하여 JSON 파일로 저장

실행: python scripts/fetch_data.py
환경변수: KRX_ID, KRX_PW (.env 파일에 설정)
출력: public/data/*.json
"""

import json
import os
import sys
import requests
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

from dotenv import load_dotenv
from pykrx import stock
import pandas as pd

# ─── 설정 ───────────────────────────────────────────────
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "public" / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

MARKETS = ["KOSPI", "KOSDAQ"]
INVESTORS = ["외국인", "기관합계"]

PERIODS = {
    "1d": 1,
    "1w": 5,
    "1m": 20,
    "3m": 60,
    "6m": 120,
}

UNIT = 1_000_000  # 백만원 단위


# ─── 유틸 ───────────────────────────────────────────────
def get_latest_business_day():
    """최근 영업일을 찾는다 (주말/공휴일 건너뜀)"""
    today = datetime.today().date()
    for _ in range(10):
        if today.weekday() >= 5:
            today -= timedelta(days=1)
            continue
        ymd = today.strftime("%Y%m%d")
        try:
            df = stock.get_market_ohlcv(ymd, ymd, "005930")
            if not df.empty:
                return today
        except Exception:
            pass
        today -= timedelta(days=1)
    raise RuntimeError("최근 영업일을 찾을 수 없습니다")


def get_business_days(end_date, count=200):
    """end_date 기준 과거 영업일 목록 생성"""
    start = end_date - timedelta(days=400)
    df = stock.get_market_ohlcv(
        start.strftime("%Y%m%d"),
        end_date.strftime("%Y%m%d"),
        "005930"
    )
    return sorted(df.index.tolist())


def save_json(filename, data):
    """JSON 파일 저장"""
    filepath = DATA_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, default=str)
    size_kb = filepath.stat().st_size / 1024
    print(f"  ✅ {filename} 저장 완료 ({size_kb:.1f} KB)")


# ─── 1. 종목별 순매수 ──────────────────────────────────
def fetch_stock_rankings(biz_date, biz_days):
    """
    종목별 외국인/기관 순매수 데이터 수집
    → stock-rankings.json
    """
    print("\n📊 [1/4] 종목별 순매수 수집 중...")
    date_str = biz_date.strftime("%Y%m%d")
    aggregated = defaultdict(lambda: {
        "foreign": {"1d": 0, "1w": 0, "1m": 0, "3m": 0, "6m": 0},
        "institution": {"1d": 0, "1w": 0, "1m": 0, "3m": 0, "6m": 0},
        "market": "",
    })

    for market in MARKETS:
        print(f"  📈 {market} 처리 중...")
        for period_name, num_days in PERIODS.items():
            if len(biz_days) < num_days:
                print(f"    ⚠️  {period_name}: 영업일 부족, 건너뜀")
                continue

            start_date = biz_days[-num_days].strftime("%Y%m%d")
            print(f"    {period_name}: {start_date} ~ {date_str}")

            for investor in INVESTORS:
                try:
                    df = stock.get_market_net_purchases_of_equities(
                        start_date, date_str, market, investor
                    )
                    if df is None or df.empty:
                        continue

                    df = df.reset_index()[["종목명", "순매수거래대금"]].fillna(0)
                    inv_key = "foreign" if investor == "외국인" else "institution"

                    for _, row in df.iterrows():
                        name = row["종목명"]
                        amount = round(row["순매수거래대금"] / UNIT, 1)
                        aggregated[name][inv_key][period_name] = amount
                        aggregated[name]["market"] = market

                except Exception as e:
                    print(f"    ❌ {market}/{period_name}/{investor}: {e}")

    # JSON 변환
    rankings = []
    for name, data in aggregated.items():
        f = data["foreign"]
        i = data["institution"]
        rankings.append({
            "name": name,
            "market": data["market"],
            "foreign": f,
            "institution": i,
            "combined": {
                p: round(f[p] + i[p], 1) for p in PERIODS
            },
        })

    # 1개월 외국인+기관 합산 기준 정렬
    rankings.sort(key=lambda x: x["combined"]["1m"], reverse=True)

    save_json("stock-rankings.json", {
        "date": str(biz_date),
        "unit": "백만원",
        "count": len(rankings),
        "data": rankings,
    })

    return rankings


# ─── 2. 섹터별 순매수 ──────────────────────────────────
def fetch_sector_map(biz_date):
    """
    KRX OpenAPI로 종목명 → 업종명 매핑을 가져온다.
    유가증권 종목기본정보 + 코스닥 종목기본정보 사용.
    """
    api_key = os.getenv("KRX_API_KEY", "")
    if not api_key:
        print("  ⚠️  KRX_API_KEY 없음 — 섹터 매핑 불가")
        return {}

    date_str = biz_date.strftime("%Y%m%d")
    sector_map = {}

    # 유가증권(KOSPI) + 코스닥(KOSDAQ) 종목기본정보
    endpoints = [
        ("KOSPI", "http://data-dbg.krx.co.kr/svc/apis/sto/stk_isu_base_info"),
        ("KOSDAQ", "http://data-dbg.krx.co.kr/svc/apis/sto/ksq_isu_base_info"),
    ]

    for market, url in endpoints:
        try:
            resp = requests.get(
                url,
                params={"basDd": date_str},
                headers={"AUTH_KEY": api_key},
                timeout=30,
            )
            data = resp.json()
            items = data.get("OutBlock_1", [])
            for item in items:
                name = item.get("ISU_ABBRV", "")  # 종목 약칭
                sector = item.get("IDX_IND_NM", "")  # 업종명
                if name and sector:
                    sector_map[name] = sector
            print(f"  📋 {market}: {len(items)}개 종목 매핑 완료")
        except Exception as e:
            print(f"  ❌ {market} 종목기본정보 실패: {e}")

    return sector_map


def fetch_sector_rankings(stock_rankings, biz_date):
    """
    종목별 순매수 데이터를 업종별로 집계
    → sector-rankings.json
    """
    print("\n📊 [2/4] 섹터별 순매수 집계 중...")

    # 1. KRX OpenAPI로 종목 → 업종 매핑
    sector_map = fetch_sector_map(biz_date)

    if not sector_map:
        print("  ⚠️  섹터 매핑이 비어있어 건너뜁니다")
        save_json("sector-rankings.json", {
            "date": str(biz_date), "unit": "백만원", "count": 0, "data": [],
        })
        return

    # 2. 종목별 데이터를 업종별로 합산
    sector_data = defaultdict(lambda: {
        "foreign": {p: 0 for p in PERIODS},
        "institution": {p: 0 for p in PERIODS},
        "stock_count": 0,
    })

    mapped = 0
    for s in stock_rankings:
        sector = sector_map.get(s["name"])
        if not sector:
            continue
        mapped += 1
        sector_data[sector]["stock_count"] += 1
        for period in PERIODS:
            sector_data[sector]["foreign"][period] += s["foreign"][period]
            sector_data[sector]["institution"][period] += s["institution"][period]

    print(f"  📋 {mapped}/{len(stock_rankings)} 종목 매핑됨, {len(sector_data)}개 업종")

    # 3. JSON 변환
    sectors = []
    for name, data in sector_data.items():
        f = data["foreign"]
        i = data["institution"]
        sectors.append({
            "name": name,
            "stock_count": data["stock_count"],
            "foreign": {p: round(f[p], 1) for p in PERIODS},
            "institution": {p: round(i[p], 1) for p in PERIODS},
            "combined": {
                p: round(f[p] + i[p], 1) for p in PERIODS
            },
        })

    sectors.sort(key=lambda x: x["combined"]["1m"], reverse=True)

    save_json("sector-rankings.json", {
        "date": str(biz_date),
        "unit": "백만원",
        "count": len(sectors),
        "data": sectors,
    })


# ─── 3. 시장 요약 (KOSPI/KOSDAQ 전체 흐름) ─────────────
def fetch_market_overview(biz_date, biz_days):
    """
    KOSPI/KOSDAQ 시장 전체 투자자별 자금 흐름
    → market-overview.json
    """
    print("\n📊 [3/4] 시장 전체 자금흐름 수집 중...")
    date_str = biz_date.strftime("%Y%m%d")
    result = {}

    for market in MARKETS:
        market_data = {
            "index": None,
            "change": None,
            "change_pct": None,
            "flow": {},
        }

        # 지수 조회
        try:
            idx_code = "1001" if market == "KOSPI" else "2001"
            idx_df = stock.get_index_ohlcv(date_str, date_str, idx_code)
            if not idx_df.empty:
                row = idx_df.iloc[-1]
                market_data["index"] = float(row["종가"])
                market_data["change"] = float(row["등락률"]) if "등락률" in row else None
        except Exception as e:
            print(f"  ⚠️  {market} 지수 조회 실패: {e}")

        # 기간별 투자자 순매수
        for period_name, num_days in PERIODS.items():
            if len(biz_days) < num_days:
                continue
            start_str = biz_days[-num_days].strftime("%Y%m%d")

            try:
                df = stock.get_market_trading_value_by_date(
                    start_str, date_str, market
                )
                if df is None or df.empty:
                    continue

                market_data["flow"][period_name] = {
                    "foreign": round(df["외국인합계"].sum() / UNIT, 1) if "외국인합계" in df.columns else 0,
                    "institution": round(df["기관합계"].sum() / UNIT, 1) if "기관합계" in df.columns else 0,
                    "individual": round(df["개인"].sum() / UNIT, 1) if "개인" in df.columns else 0,
                }
            except Exception as e:
                print(f"  ⚠️  {market}/{period_name} 흐름 실패: {e}")

        result[market] = market_data

    save_json("market-overview.json", {
        "date": str(biz_date),
        "unit": "백만원",
        "data": result,
    })


# ─── 4. 메타 정보 ──────────────────────────────────────
def save_meta(biz_date):
    """마지막 업데이트 시간 기록"""
    print("\n📊 [4/4] 메타 정보 저장...")
    save_json("meta.json", {
        "last_updated": datetime.now().isoformat(),
        "business_date": str(biz_date),
        "version": "2.0",
    })


# ─── 메인 ──────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("🚀 Jangstrading v2 — 데이터 수집 시작")
    print("=" * 50)

    try:
        biz_date = get_latest_business_day()
        print(f"\n📅 기준 영업일: {biz_date}")

        biz_days = get_business_days(biz_date)
        print(f"📅 영업일 목록: {len(biz_days)}일")

        # 1. 종목별 순매수
        stock_rankings = fetch_stock_rankings(biz_date, biz_days)

        # 2. 섹터별 순매수
        fetch_sector_rankings(stock_rankings, biz_date)

        # 3. 시장 요약
        fetch_market_overview(biz_date, biz_days)

        # 4. 메타 정보
        save_meta(biz_date)

        print("\n" + "=" * 50)
        print("✅ 모든 데이터 수집 완료!")
        print(f"📁 저장 경로: {DATA_DIR}")
        print("=" * 50)

    except Exception as e:
        print(f"\n❌ 치명적 에러: {e}")
        sys.exit(1)
