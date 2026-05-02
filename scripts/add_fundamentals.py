"""
기존 stock-rankings.json에 PER, PBR 데이터를 추가하는 스크립트
pykrx의 get_market_fundamental_by_ticker() 사용

실행: python scripts/add_fundamentals.py
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

    # PER/PBR 데이터 수집
    fundamentals = {}
    for market in ["KOSPI", "KOSDAQ"]:
        try:
            df = stock.get_market_fundamental(biz_date, market=market)
            if df is not None and not df.empty:
                df = df.reset_index()
                for _, row in df.iterrows():
                    ticker = row["티커"] if "티커" in row else str(row.name)
                    per = row.get("PER", None)
                    pbr = row.get("PBR", None)
                    if per is not None:
                        fundamentals[ticker] = {
                            "per": round(float(per), 2) if per and per > 0 else None,
                            "pbr": round(float(pbr), 2) if pbr and pbr > 0 else None,
                        }
            print(f"  📋 {market}: {len(df)}개 종목 PER/PBR 로드")
        except Exception as e:
            print(f"  ❌ {market} 실패: {e}")

    # stock-rankings.json에 PER/PBR 추가
    matched = 0
    for item in data["data"]:
        ticker = item.get("ticker", "")
        if ticker and ticker in fundamentals:
            item["per"] = fundamentals[ticker]["per"]
            item["pbr"] = fundamentals[ticker]["pbr"]
            matched += 1
        else:
            item["per"] = None
            item["pbr"] = None

    print(f"  ✅ {matched}/{len(data['data'])} 종목 PER/PBR 매칭 완료")

    with open(rankings_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, default=str)

    size_kb = rankings_path.stat().st_size / 1024
    print(f"  ✅ stock-rankings.json 갱신 완료 ({size_kb:.1f} KB)")

if __name__ == "__main__":
    main()
