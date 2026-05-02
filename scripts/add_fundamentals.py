"""
stock-rankings.json에 재무 지표를 추가하는 스크립트
PER, PBR, EPS, BPS, 배당수익률, 시가총액

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

    # 1. PER/PBR/EPS/BPS/DIV 수집
    fundamentals = {}
    for market in ["KOSPI", "KOSDAQ"]:
        try:
            df = stock.get_market_fundamental(biz_date, market=market)
            if df is not None and not df.empty:
                # 컬럼 확인 (디버깅)
                print(f"  📋 {market} 재무지표 컬럼: {list(df.columns)}")
                print(f"  📋 {market} 샘플 데이터:")
                print(df.head(3))

                for ticker in df.index:
                    row = df.loc[ticker]
                    # 컬럼명 유연하게 처리
                    per = float(row.get("PER", 0) or 0)
                    pbr = float(row.get("PBR", 0) or 0)
                    eps = float(row.get("EPS", 0) or 0)
                    bps = float(row.get("BPS", 0) or 0)
                    div_yield = float(row.get("DIV", 0) or 0)

                    fundamentals[ticker] = {
                        "per": round(per, 2) if per > 0 else None,
                        "pbr": round(pbr, 2) if pbr > 0 else None,
                        "eps": int(eps) if eps != 0 else None,
                        "bps": int(bps) if bps > 0 else None,
                        "div_yield": round(div_yield, 2) if div_yield > 0 else None,
                    }
                print(f"  ✅ {market}: {len(df)}개 종목 재무지표 로드")
        except Exception as e:
            print(f"  ❌ {market} 재무지표 실패: {e}")
            import traceback
            traceback.print_exc()

    # 2. 시가총액 수집
    marcap = {}
    for market in ["KOSPI", "KOSDAQ"]:
        try:
            df = stock.get_market_cap(biz_date, market=market)
            if df is not None and not df.empty:
                print(f"  📋 {market} 시총 컬럼: {list(df.columns)}")
                print(f"  📋 {market} 시총 샘플:")
                print(df.head(3))

                for ticker in df.index:
                    row = df.loc[ticker]
                    cap = int(row.get("시가총액", 0) or 0)
                    marcap[ticker] = cap
                print(f"  ✅ {market}: {len(df)}개 종목 시가총액 로드")
        except Exception as e:
            print(f"  ❌ {market} 시가총액 실패: {e}")
            import traceback
            traceback.print_exc()

    # 3. stock-rankings.json에 추가
    matched_fund = 0
    matched_cap = 0
    for item in data["data"]:
        ticker = item.get("ticker", "")

        # 재무지표
        if ticker and ticker in fundamentals:
            f = fundamentals[ticker]
            item["per"] = f["per"]
            item["pbr"] = f["pbr"]
            item["eps"] = f["eps"]
            item["bps"] = f["bps"]
            item["div_yield"] = f["div_yield"]
            matched_fund += 1
        else:
            item.setdefault("per", None)
            item.setdefault("pbr", None)
            item.setdefault("eps", None)
            item.setdefault("bps", None)
            item.setdefault("div_yield", None)

        # 시가총액 (억원 단위)
        if ticker and ticker in marcap:
            item["market_cap"] = round(marcap[ticker] / 100_000_000, 0)
            matched_cap += 1
        else:
            item.setdefault("market_cap", None)

    print(f"\n  ✅ 재무지표: {matched_fund}/{len(data['data'])} 매칭")
    print(f"  ✅ 시가총액: {matched_cap}/{len(data['data'])} 매칭")

    with open(rankings_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, default=str)

    size_kb = rankings_path.stat().st_size / 1024
    print(f"  ✅ stock-rankings.json 갱신 완료 ({size_kb:.1f} KB)")

if __name__ == "__main__":
    main()
