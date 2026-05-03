"""
종목별 외국인/기관 추정 평균단가를 계산하는 스크립트
이동평균 원가법 (Moving Average Cost) 사용

매수일: 새 평균단가 = (기존단가 × 기존수량 + 당일VWAP × 매수수량) / (기존수량 + 매수수량)
매도일: 평균단가 유지, 보유수량만 감소

실행: python scripts/add_avg_cost.py
"""

import json
from pathlib import Path
from dotenv import load_dotenv
from pykrx import stock
from datetime import datetime, timedelta

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "public" / "data"

LOOKBACK_DAYS = 120  # 약 6개월


def calc_moving_avg_cost(daily_data):
    """
    이동평균 원가법으로 추정 평균단가를 계산

    daily_data: list of (date, net_volume, vwap)
      - net_volume: 순매수 수량 (양수=매수, 음수=매도)
      - vwap: 해당일 거래대금/거래량 (당일 평균 체결가 추정)

    Returns: (avg_cost, position) or (None, 0)
    """
    avg_cost = 0.0
    position = 0  # 현재 보유 수량

    for date, net_vol, vwap in daily_data:
        if vwap <= 0:
            continue

        if net_vol > 0:
            # 매수: 평균단가 갱신
            total_cost = avg_cost * position + vwap * net_vol
            position += net_vol
            if position > 0:
                avg_cost = total_cost / position
        elif net_vol < 0:
            # 매도: 평균단가 유지, 수량 감소
            position += net_vol  # net_vol is negative
            if position <= 0:
                # 포지션 청산 — 평균단가 리셋
                avg_cost = 0.0
                position = 0

    if position <= 0 or avg_cost <= 0:
        return None, 0

    return round(avg_cost, 0), position


def main():
    rankings_path = DATA_DIR / "stock-rankings.json"
    with open(rankings_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    biz_date = data["date"].replace("-", "")
    end_dt = datetime.strptime(biz_date, "%Y%m%d")
    start_dt = end_dt - timedelta(days=LOOKBACK_DAYS * 1.5)
    start_str = start_dt.strftime("%Y%m%d")

    print(f"📅 기준일: {data['date']}")
    print(f"📅 조회 범위: {start_str} ~ {biz_date} ({LOOKBACK_DAYS}영업일)")

    # 티커 목록 (상위 300종목만 — API 호출 절약)
    tickers_to_calc = []
    sorted_stocks = sorted(data["data"], key=lambda x: abs(x.get("combined", {}).get("1m", 0)), reverse=True)
    for item in sorted_stocks:
        t = item.get("ticker", "")
        if t and (item.get("market_cap") or 0) >= 500:  # 시총 500억 이상
            tickers_to_calc.append((t, item["name"]))
        if len(tickers_to_calc) >= 500:
            break

    print(f"📊 {len(tickers_to_calc)}개 종목 평균단가 계산 시작...")

    avg_costs = {}
    done = 0

    for ticker, name in tickers_to_calc:
        try:
            # 일별 투자자별 거래량
            df_vol = stock.get_market_trading_volume_by_date(start_str, biz_date, ticker)
            if df_vol is None or df_vol.empty:
                continue

            # 일별 OHLCV (VWAP 계산용)
            df_ohlcv = stock.get_market_ohlcv(start_str, biz_date, ticker)
            if df_ohlcv is None or df_ohlcv.empty:
                continue

            # 현재 종가
            current_price = float(df_ohlcv.iloc[-1]["종가"])
            if current_price <= 0:
                continue

            result = {"price": current_price}

            for inv_col, inv_key in [("외국인합계", "foreign"), ("기관합계", "institution")]:
                if inv_col not in df_vol.columns:
                    continue

                daily = []
                for date in df_vol.index:
                    net_vol = int(df_vol.loc[date, inv_col])
                    if date in df_ohlcv.index:
                        row = df_ohlcv.loc[date]
                        volume = float(row.get("거래량", 0))
                        if volume > 0:
                            # VWAP = 거래대금 / 거래량 (없으면 종가 사용)
                            trade_val = float(row.get("거래대금", 0))
                            vwap = trade_val / volume if trade_val > 0 else float(row["종가"])
                        else:
                            vwap = float(row["종가"])
                        daily.append((date, net_vol, vwap))

                avg_cost, position = calc_moving_avg_cost(daily)
                if avg_cost and avg_cost > 0:
                    pnl_pct = round((current_price - avg_cost) / avg_cost * 100, 2)
                    result[inv_key] = {
                        "avg_cost": int(avg_cost),
                        "pnl_pct": pnl_pct,
                    }

            if "foreign" in result or "institution" in result:
                avg_costs[ticker] = result

            done += 1
            if done % 50 == 0:
                print(f"  ... {done}/{len(tickers_to_calc)} 완료")

        except Exception as e:
            continue

    print(f"  ✅ {len(avg_costs)}개 종목 평균단가 계산 완료")

    # stock-rankings.json에 추가
    matched = 0
    for item in data["data"]:
        ticker = item.get("ticker", "")
        if ticker and ticker in avg_costs:
            item["avg_cost"] = avg_costs[ticker]
            matched += 1
        else:
            item.setdefault("avg_cost", None)

    print(f"  ✅ {matched}/{len(data['data'])} 종목 매칭 완료")

    with open(rankings_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, default=str)

    size_kb = rankings_path.stat().st_size / 1024
    print(f"  ✅ stock-rankings.json 갱신 완료 ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
