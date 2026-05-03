"""
stock-rankings.json에 주가 수익률 데이터를 추가하는 스크립트
수급 전환 신호 + 수급/주가 괴리 분석에 사용

실행: python scripts/add_price_changes.py
"""

import json
from pathlib import Path
from dotenv import load_dotenv
from pykrx import stock

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "public" / "data"

def main():
    rankings_path = DATA_DIR / "stock-rankings.json"
    with open(rankings_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    biz_date = data["date"].replace("-", "")
    print(f"📅 기준일: {data['date']}")

    # 각 종목의 기간별 수익률 수집
    price_changes = {}
    periods = {"1w": 5, "1m": 20, "3m": 60}

    for market in ["KOSPI", "KOSDAQ"]:
        try:
            # 현재일 종가
            df_today = stock.get_market_ohlcv(biz_date, market=market)
            if df_today is None or df_today.empty:
                continue

            for period_name, days in periods.items():
                # 과거 날짜 계산 (영업일 기준으로 대략 추정)
                from datetime import datetime, timedelta
                past_date = datetime.strptime(biz_date, "%Y%m%d") - timedelta(days=int(days * 1.5))
                past_str = past_date.strftime("%Y%m%d")

                df_past = stock.get_market_ohlcv(past_str, market=market)
                if df_past is None or df_past.empty:
                    continue

                for ticker in df_today.index:
                    if ticker not in df_past.index:
                        continue

                    close_today = float(df_today.loc[ticker, "종가"])
                    close_past = float(df_past.loc[ticker, "종가"])

                    if close_past <= 0:
                        continue

                    change_pct = round((close_today - close_past) / close_past * 100, 2)

                    if ticker not in price_changes:
                        price_changes[ticker] = {}
                    price_changes[ticker][period_name] = change_pct

            print(f"  ✅ {market}: 수익률 계산 완료")
        except Exception as e:
            print(f"  ❌ {market} 수익률 실패: {e}")

    # stock-rankings.json에 추가
    matched = 0
    for item in data["data"]:
        ticker = item.get("ticker", "")
        if ticker and ticker in price_changes:
            item["price_change"] = price_changes[ticker]
            matched += 1
        else:
            item.setdefault("price_change", {})

    print(f"  ✅ {matched}/{len(data['data'])} 종목 수익률 매칭 완료")

    with open(rankings_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, default=str)

    size_kb = rankings_path.stat().st_size / 1024
    print(f"  ✅ stock-rankings.json 갱신 완료 ({size_kb:.1f} KB)")

if __name__ == "__main__":
    main()
