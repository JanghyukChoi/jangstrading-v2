"""
기존 stock-rankings.json에 티커 코드를 추가하는 스크립트
TradingView 차트 연동에 필요

실행: python scripts/add_tickers.py
"""

import json
from pathlib import Path
from dotenv import load_dotenv
from pykrx import stock

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "public" / "data"

def main():
    # 1. 기존 stock-rankings.json 로드
    rankings_path = DATA_DIR / "stock-rankings.json"
    with open(rankings_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    biz_date = data["date"].replace("-", "")
    print(f"📅 기준일: {data['date']}")

    # 2. 티커 → 종목명 매핑 구축
    name_to_ticker = {}
    for market in ["KOSPI", "KOSDAQ"]:
        tickers = stock.get_market_ticker_list(biz_date, market=market)
        for ticker in tickers:
            name = stock.get_market_ticker_name(ticker)
            name_to_ticker[name] = ticker
        print(f"  📋 {market}: {len(tickers)}개 티커 로드")

    # 3. 각 종목에 ticker 필드 추가
    matched = 0
    for item in data["data"]:
        ticker = name_to_ticker.get(item["name"], "")
        item["ticker"] = ticker
        if ticker:
            matched += 1

    print(f"  ✅ {matched}/{len(data['data'])} 종목 티커 매칭 완료")

    # 4. 저장
    with open(rankings_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, default=str)

    size_kb = rankings_path.stat().st_size / 1024
    print(f"  ✅ stock-rankings.json 갱신 완료 ({size_kb:.1f} KB)")

if __name__ == "__main__":
    main()
