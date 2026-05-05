"""
종목별 기관 세부 주체 데이터를 기간별로 수집하는 스크립트
5개 기간 × 6주체 × 2시장 = 60번 API 호출, ~2분

실행: python scripts/add_inst_detail.py
"""

import json
from pathlib import Path
from dotenv import load_dotenv
from pykrx import stock
from datetime import datetime, timedelta

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "public" / "data"

INVESTORS = ["금융투자", "보험", "투신", "사모", "은행", "연기금"]
PERIODS = {
    "1d": 1,
    "1w": 7,
    "1m": 30,
    "3m": 90,
    "6m": 180,
}


def main():
    rankings_path = DATA_DIR / "stock-rankings.json"
    with open(rankings_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    biz_date = data["date"].replace("-", "")
    end_dt = datetime.strptime(biz_date, "%Y%m%d")

    print(f"📅 기준일: {data['date']}")
    print(f"📊 기관 세부: 5기간 × 6주체 × 2시장 = 60번 API 호출")

    # 티커 → { "1d": {주체: 금액}, "1w": {...}, ... }
    inst_data = {}

    for period_name, days in PERIODS.items():
        start_dt = end_dt - timedelta(days=days)
        start_str = start_dt.strftime("%Y%m%d")
        print(f"\n  📅 {period_name} ({start_str} ~ {biz_date})")

        for market in ["KOSPI", "KOSDAQ"]:
            for inv in INVESTORS:
                try:
                    df = stock.get_market_net_purchases_of_equities_by_ticker(
                        start_str, biz_date, market, inv
                    )
                    if df is None or df.empty:
                        continue

                    for ticker in df.index:
                        val = float(df.loc[ticker, "순매수거래대금"])
                        val_m = round(val / 1_000_000, 1)

                        if ticker not in inst_data:
                            inst_data[ticker] = {}
                        if period_name not in inst_data[ticker]:
                            inst_data[ticker][period_name] = {}
                        inst_data[ticker][period_name][inv] = val_m

                except Exception as e:
                    print(f"    ❌ {market}/{inv} 실패: {e}")

        print(f"    ✅ {period_name} 완료")

    print(f"\n📋 총 {len(inst_data)}개 종목 기관 세부 수집 완료")

    # stock-rankings.json에 추가
    matched = 0
    for item in data["data"]:
        ticker = item.get("ticker", "")
        if ticker and ticker in inst_data:
            item["inst_detail"] = inst_data[ticker]
            # 연기금 데이터를 별도 필드로 추출 (종목 순매수 페이지용)
            pension = {}
            for p in PERIODS:
                if p in inst_data[ticker] and "연기금" in inst_data[ticker][p]:
                    pension[p] = inst_data[ticker][p]["연기금"]
            if pension:
                item["pension"] = pension
            matched += 1

    print(f"✅ {matched}/{len(data['data'])} 종목 매칭 완료")

    with open(rankings_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, default=str)

    size_kb = rankings_path.stat().st_size / 1024
    print(f"✅ stock-rankings.json 갱신 완료 ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
