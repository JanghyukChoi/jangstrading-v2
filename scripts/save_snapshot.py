"""
일일 스냅샷 저장 스크립트
수급 신호 발생 종목 + 전 종목 종가 + Breadth + 시장 지수

저장: public/data/snapshots/YYYY-MM-DD.json
용량: 하루 ~56KB, 1년 ~15MB

실행: python scripts/save_snapshot.py
"""

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "public" / "data"
SNAP_DIR = DATA_DIR / "snapshots"


def main():
    rankings_path = DATA_DIR / "stock-rankings.json"
    with open(rankings_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    stocks = data["data"]
    date = data["date"]

    print(f"📸 스냅샷 저장 시작 ({date})")

    # 1. 수급 신호 판정
    big = [s for s in stocks if (s.get("market_cap") or 0) >= 1000]
    signals = {"buy_reversal": [], "sell_reversal": [], "divergence": [], "accumulation": []}

    for s in big:
        t = s.get("ticker", "")
        if not t:
            continue
        c = s["combined"]
        pc = s.get("price_change", {})

        if c.get("3m", 0) < -5000 and c.get("1w", 0) > 500:
            signals["buy_reversal"].append(t)
        if c.get("3m", 0) > 5000 and c.get("1w", 0) < -500:
            signals["sell_reversal"].append(t)
        if c.get("1m", 0) > 5000 and (pc.get("1m", 0) or 0) < -5:
            signals["divergence"].append(t)
        if c.get("1d", 0) > 50 and c.get("1w", 0) > 500 and c.get("1m", 0) > 5000:
            signals["accumulation"].append(t)

    # 2. 전 종목 종가
    prices = {}
    for s in stocks:
        t = s.get("ticker", "")
        if t and s.get("avg_cost"):
            prices[t] = s["avg_cost"].get("price", 0)

    # 종가가 avg_cost에 없는 경우 대비
    if len(prices) < 100:
        # price_change에서 역산 불가하므로 빈 dict 유지
        pass

    # 3. 수급 Breadth (1일 기준)
    foreign_buy = sum(1 for s in stocks if s["foreign"].get("1d", 0) > 0)
    foreign_sell = sum(1 for s in stocks if s["foreign"].get("1d", 0) < 0)
    inst_buy = sum(1 for s in stocks if s["institution"].get("1d", 0) > 0)
    inst_sell = sum(1 for s in stocks if s["institution"].get("1d", 0) < 0)

    breadth = {
        "foreign_buy": foreign_buy,
        "foreign_sell": foreign_sell,
        "inst_buy": inst_buy,
        "inst_sell": inst_sell,
    }

    # 4. 시장 지수
    market = {}
    try:
        with open(DATA_DIR / "market-overview.json", "r", encoding="utf-8") as f:
            mo = json.load(f)["data"]
        for m in ["KOSPI", "KOSDAQ"]:
            idx = mo.get(m, {}).get("index")
            if isinstance(idx, dict):
                market[m.lower()] = idx.get("value", 0)
            elif isinstance(idx, (int, float)):
                market[m.lower()] = idx
    except Exception:
        pass

    # 5. 저장
    snapshot = {
        "date": date,
        "signals": signals,
        "prices": prices,
        "breadth": breadth,
        "market": market,
    }

    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    snap_path = SNAP_DIR / f"{date}.json"
    with open(snap_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False)

    size_kb = snap_path.stat().st_size / 1024
    print(f"  📊 신호: 매수전환 {len(signals['buy_reversal'])} | 매도전환 {len(signals['sell_reversal'])} | 괴리 {len(signals['divergence'])} | 집중매수 {len(signals['accumulation'])}")
    print(f"  💰 종가: {len(prices)}종목")
    print(f"  📈 Breadth: 외국인 +{breadth['foreign_buy']}/-{breadth['foreign_sell']} | 기관 +{breadth['inst_buy']}/-{breadth['inst_sell']}")
    print(f"  ✅ {snap_path} 저장 완료 ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
