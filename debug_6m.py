from dotenv import load_dotenv
load_dotenv()
from pykrx import stock
from datetime import datetime, timedelta

biz = "20260430"
target = datetime(2026, 4, 30) - timedelta(days=int(120 * 1.5))
print(f"6m 타겟 날짜: {target.strftime('%Y%m%d')}")

for offset in range(8):
    d = (target - timedelta(days=offset)).strftime("%Y%m%d")
    df = stock.get_market_ohlcv(d, market="KOSPI")
    if df is not None and not df.empty:
        print(f"영업일 발견: {d}, {len(df)}종목")
        today = stock.get_market_ohlcv(biz, market="KOSPI")
        t = "005930"
        print(f"삼성전자 과거종가: {df.loc[t, '종가']}, 현재종가: {today.loc[t, '종가']}")
        pct = round((today.loc[t, '종가'] - df.loc[t, '종가']) / df.loc[t, '종가'] * 100, 2)
        print(f"수익률: {pct}%")
        break
    else:
        print(f"{d} 데이터 없음, 다음 시도...")
