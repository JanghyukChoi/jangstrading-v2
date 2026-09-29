"""
종목별 변동성과 분위를 계산해 public/data/volatility.json 으로 내보낸다.

무엇을 재는가
  backtest_longfactors.py / backtest_lowrisk.py 에서 검정한 것과 **같은 정의**를
  써야 한다. 화면에 다른 숫자를 쓰면 검정하지 않은 것을 보여주는 셈이 된다.

    순위용   252일 일간수익률 표준편차 (연율화)   <- 백테스트가 쓴 값
    표시용   252일 일간수익률 절대값 평균         <- "하루 평균 ±X%" 는 이쪽이
                                                   말 그대로 사실이다

  표준편차를 "하루 평균 ±X%" 라고 쓰면 엄밀히는 틀린 말이라 표시용을 따로 둔다.

분위 기준 모집단
  **시가총액 1,000억 이상**. 백테스트 유니버스와 같아야 한다. 전 종목으로
  순위를 매기면 화면의 "상위 10%" 와 검정된 "상위 10%" 가 다른 집단이 된다.

산출
  {
    "date": "2026-09-23",
    "universe": 1379,                  # 분위 계산에 쓴 종목 수
    "data": { "005930": {
        "vol": 0.284,                  # 연율화 표준편차
        "daily": 1.42,                 # 하루 평균 변동폭 %
        "pct": 63,                     # 백분위 (1 = 가장 잠잠, 100 = 가장 요동)
        "top": false                   # 상위 10% 여부
    }, ... }
  }

실행
  python scripts/build_volatility.py
"""

import json
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "public" / "data"
TS = DATA / "timeseries"
OUT = DATA / "volatility.json"

WINDOW = 252            # 백테스트와 동일
MIN_DAYS = 200          # 이보다 짧으면 신뢰할 수 없다(신규상장 등)
MIN_MCAP_EOK = 1000     # 억원. 백테스트 유니버스 = 시총 1,000억 이상
LIMIT = 0.45            # ±30% 제한 밖은 분할·병합·데이터오류로 보고 버린다


def daily_returns(prices):
    """가격 배열 -> 일간수익률. 비정상 점프는 버린다."""
    out = []
    for i in range(1, len(prices)):
        p0, p1 = prices[i - 1], prices[i]
        if not p0 or not p1 or p0 <= 0 or p1 <= 0:
            continue
        r = p1 / p0 - 1.0
        if abs(r) > LIMIT:
            continue          # 액면분할 등 — 수익률이 아니다
        out.append(r)
    return out


def main():
    rk_path = DATA / "stock-rankings.json"
    try:
        rk = json.loads(rk_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        print("stock-rankings.json 을 읽을 수 없습니다.")
        return 1
    mcap = {s["ticker"]: (s.get("market_cap") or 0)
            for s in rk.get("data", []) if s.get("ticker")}

    rows = {}
    skipped_short = 0
    for p in TS.glob("*.json"):
        tk = p.stem
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        prices = (d.get("prices") or [])[-(WINDOW + 1):]
        rets = daily_returns(prices)
        if len(rets) < MIN_DAYS:
            skipped_short += 1
            continue
        n = len(rets)
        mean = sum(rets) / n
        var = sum((x - mean) ** 2 for x in rets) / n
        vol = var ** 0.5 * (252 ** 0.5)
        daily = sum(abs(x) for x in rets) / n * 100
        rows[tk] = {"vol": round(vol, 4), "daily": round(daily, 2)}

    # 분위는 백테스트 유니버스(시총 1,000억+) 안에서만 매긴다.
    ranked = [t for t in rows if mcap.get(t, 0) >= MIN_MCAP_EOK]
    ranked.sort(key=lambda t: rows[t]["vol"])
    m = len(ranked)
    for i, t in enumerate(ranked):
        pct = int(round((i + 0.5) / m * 100))
        rows[t]["pct"] = max(1, min(100, pct))
        rows[t]["top"] = pct >= 91          # 상위 10%
    # 유니버스 밖(소형주)은 분위를 주지 않는다. 검정된 집단이 아니다.
    for t in rows:
        rows[t].setdefault("pct", None)
        rows[t].setdefault("top", False)

    out = {"date": rk.get("date", ""), "window": WINDOW,
           "universe": m, "min_market_cap_eok": MIN_MCAP_EOK, "data": rows}
    OUT.write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")

    tops = [t for t in ranked if rows[t]["top"]]
    print(f"변동성 계산 {len(rows)}종목 (짧은 이력 제외 {skipped_short})")
    print(f"  분위 모집단 {m}종목 (시총 {MIN_MCAP_EOK}억 이상)")
    print(f"  상위 10% = {len(tops)}종목")
    if tops:
        names = {s["ticker"]: s["name"] for s in rk["data"] if s.get("ticker")}
        ex = sorted(tops, key=lambda t: -rows[t]["vol"])[:5]
        for t in ex:
            print(f"    {names.get(t, t):14s} 하루 평균 ±{rows[t]['daily']:.1f}%  "
                  f"상위 {101 - rows[t]['pct']}%")
    lows = ranked[:3]
    for t in lows:
        names = {s["ticker"]: s["name"] for s in rk["data"] if s.get("ticker")}
        print(f"  (가장 잠잠) {names.get(t, t):12s} 하루 평균 ±{rows[t]['daily']:.1f}%")
    print(f"  -> {OUT.relative_to(BASE)} ({OUT.stat().st_size/1024:.0f}KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
