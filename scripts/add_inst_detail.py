"""
종목별 기관 세부 주체 데이터를 수집하는 스크립트
연기금/금융투자/보험/투신/사모/은행 6개 주체의 1개월 순매수

시장 전체 조회 방식: 6주체 × 2시장 = 12번 API 호출로 전체 종목 커버
소요 시간: ~30초

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


def main():
    rankings_path = DATA_DIR / "stock-rankings.json"
    with open(rankings_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    biz_date = data["date"].replace("-", "")
    end_dt = datetime.strptime(biz_date, "%Y%m%d")
    start_dt = end_dt - timedelta(days=30)
    start_str = start_dt.strftime("%Y%m%d")

    print(f"📅 기준일: {data['date']}")
    print(f"📅 조회 범위: {start_str} ~ {biz_date} (1개월)")
    print(f"📊 기관 세부 6개 주체 × 2개 시장 = 12번 API 호출")

    # 티커 → {주체: 순매수대금} 매핑
    inst_data = {}

    for market in ["KOSPI", "KOSDAQ"]:
        for inv in INVESTORS:
            try:
                df = stock.get_market_net_purchases_of_equities_by_ticker(
                    start_str, biz_date, market, inv
                )
                if df is None or df.empty:
                    print(f"  ⚠️ {market}/{inv}: 데이터 없음")
                    continue

                count = 0
                for ticker in df.index:
                    val = float(df.loc[ticker, "순매수거래대금"])
                    # 백만원 단위로 변환
                    val_m = round(val / 1_000_000, 1)

                    if ticker not in inst_data:
                        inst_data[ticker] = {}
                    inst_data[ticker][inv] = val_m
                    count += 1

                print(f"  ✅ {market}/{inv}: {count}종목")

            except Exception as e:
                print(f"  ❌ {market}/{inv} 실패: {e}")

    print(f"\n📋 총 {len(inst_data)}개 종목 기관 세부 수집 완료")

    # stock-rankings.json에 추가
    matched = 0
    for item in data["data"]:
        ticker = item.get("ticker", "")
        if ticker and ticker in inst_data:
            item["inst_detail"] = inst_data[ticker]
            matched += 1

    print(f"✅ {matched}/{len(data['data'])} 종목 매칭 완료")

    with open(rankings_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, default=str)

    size_kb = rankings_path.stat().st_size / 1024
    print(f"✅ stock-rankings.json 갱신 완료 ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
