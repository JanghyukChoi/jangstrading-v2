"""
장기수급상위(ai_screener)를 나머지 4종과 같은 기계로 검정한다.

4종은 내렸지만 이건 검정한 적이 없어 남겨 뒀다. 같은 잣대로 재야 판단이 된다.
  - 액면분할 보정된 가격 (price_adjust)
  - 보정 불가 단절 구간 제외
  - **같은 날 같은 시총 하한 모집단의 평균을 뺀 초과수익** (원수익률 아님)
  - train(~2022) / test(2023~) 분리
  - 거래비용 왕복 0.5%

구조가 달라서 run_backtest 를 못 쓴다. 이건 두 단계다 — 그날 조건을 통과한
종목들의 raw factor 를 먼저 모으고, 그 안에서 백분위를 매겨 합성한다.

사전 예상은 나쁘다. 이 신호는 **연기금 60일 순매수 >= 5bp** 를 필수 조건으로
걸고 12-1·60일 모멘텀 양수를 요구하는데,
  - 사내 원장(152팩터 장기 검정): 연기금은 예측력이 있으나 **방향이 반대**다
    (t(h=20) -4.49, 순수익 60일 -47.8bp, 단조성 rho -0.78). 가격 비탄력적
    자산배분 리밸런싱이라 종목 정보가 없다는 해석.
  - 이 저장소 대조군: 60일 모멘텀 상위 30종목 매수는 20일 초과 -2.38%(t=-23)
    로 전 구간 패배.
예상이 빗나가면 그것도 기록한다.

실행: python scripts/backtest_longterm_check.py [--top-n 5]
"""

import argparse
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backtest_signals import (  # noqa: E402
    MAX_LOOKBACK,
    TC_ROUNDTRIP,
    TRAIN_END_DATE,
    _mcap_at,
    ai_screener_factors,
    composite_ai_screener_pct,
    date_to_idx,
    load_all_timeseries,
    spans_break,
)

MCAP_FLOOR = 50_000_000_000   # ai_screener_factors 가 거는 하한과 같아야 한다
HOLDS = (5, 20, 60)           # 60일 보유 전제의 신호라 장기까지 본다


def universe_forward(timeseries, holds):
    """날짜별 '시총 하한을 넘는 종목들'의 평균 forward 수익률 = 벤치마크."""
    acc = {h: defaultdict(list) for h in holds}
    for data in timeseries.values():
        prices = data.get("prices") or []
        dates = data.get("dates") or []
        for i, d in enumerate(dates):
            p0 = prices[i] if i < len(prices) else None
            if not p0 or p0 <= 0 or i < 252:
                continue
            m = _mcap_at(data, i)
            if m is None or m < MCAP_FLOOR:
                continue
            for h in holds:
                j = i + h
                if j >= len(prices) or spans_break(data, i, j):
                    continue
                p1 = prices[j]
                if p1 and p1 > 0:
                    acc[h][d].append(p1 / p0 - 1)
    return {h: {d: sum(v) / len(v) for d, v in a.items() if v} for h, a in acc.items()}


def nw_t(series, lag):
    """날짜 시계열에 대한 Newey-West t. 중첩 보유는 자기상관이 있어 단순 t 가 부풀려진다."""
    n = len(series)
    if n < 10:
        return float("nan")
    m = sum(series) / n
    e = [x - m for x in series]
    var = sum(v * v for v in e) / n
    for L in range(1, min(lag, n - 1) + 1):
        c = sum(e[i + L] * e[i] for i in range(n - L)) / n
        var += 2 * (1 - L / (lag + 1)) * c
    if var <= 0:
        return float("nan")
    return m / (var / n) ** 0.5


def by_date(rows, bench, h, lo="", hi=""):
    """날짜별 평균 초과수익 시계열. 같은 날 여러 종목은 한 관측으로 묶는다.

    이게 정직한 단위다. 60일 보유를 11,000 거래로 세면 독립 관측이 42개뿐인데
    11,000개처럼 t 가 나온다.
    """
    acc = defaultdict(list)
    for r in rows:
        d = r["date"]
        if r.get(h) is None or d not in bench[h]:
            continue
        if (lo and d <= lo) or (hi and d > hi):
            continue
        acc[d].append(r[h] - bench[h][d])
    return [sum(v) / len(v) for _, v in sorted(acc.items())]


def stats(xs):
    if len(xs) < 30:
        return None
    m = sum(xs) / len(xs)
    sd = statistics.stdev(xs)
    return {
        "n": len(xs),
        "avg": m,
        "median": statistics.median(xs),
        "win": sum(1 for x in xs if x > 0) / len(xs),
        "t": m / (sd / len(xs) ** 0.5) if sd else 0.0,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-n", type=int, default=5, help="사이트와 동일 (LONGTERM_TOP_N)")
    args = ap.parse_args()

    ts = load_all_timeseries()
    print("벤치마크 계산 중...")
    t0 = time.time()
    bench = universe_forward(ts, HOLDS)
    print(f"  {len(bench[HOLDS[0]])}일 ({time.time() - t0:.0f}s)")

    all_dates = set()
    for d in ts.values():
        all_dates.update(d.get("dates") or [])
    eval_dates = sorted(all_dates)

    print(f"\nai_screener 백테스트 (top-{args.top_n}) — {len(eval_dates)}영업일")
    t0 = time.time()
    rows = []
    for n, date in enumerate(eval_dates, 1):
        cands = []
        for ticker, data in ts.items():
            idx = date_to_idx(data, date)
            if idx is None or spans_break(data, idx - MAX_LOOKBACK, idx):
                continue
            f = ai_screener_factors(data, idx, None)
            if f is not None:
                cands.append((ticker, idx, f))
        if len(cands) < args.top_n:
            continue
        allf = [c[2] for c in cands]
        scored = sorted(
            ((t, i, composite_ai_screener_pct(f, allf)) for t, i, f in cands),
            key=lambda x: -x[2],
        )[: args.top_n]

        for ticker, idx, score in scored:
            data = ts[ticker]
            prices = data["prices"]
            p0 = prices[idx]
            if not p0 or p0 <= 0:
                continue
            row = {"date": date, "ticker": ticker}
            for h in HOLDS:
                j = idx + h
                if j < len(prices) and not spans_break(data, idx, j):
                    p1 = prices[j]
                    row[h] = (p1 / p0 - 1) if p1 and p1 > 0 else None
                else:
                    row[h] = None
            rows.append(row)
        if n % 500 == 0:
            print(f"  {n}/{len(eval_dates)}  발화 누적 {len(rows):,}  ({time.time()-t0:.0f}s)")

    print(f"  총 발화 {len(rows):,}건 / 하루 평균 {len(rows)/max(len(eval_dates),1):.1f}건")

    print("\n초과수익 (같은 날 시총 500억 이상 종목 평균 대비)")
    print("  t 는 날짜군집 + Newey-West(lag=보유일). 같은 날 여러 종목은 한 관측.")
    print(f"{'보유':>5}{'거래':>8}{'초과':>10}{'t':>8}{'승률':>8}{'중앙값':>10}{'비용차감':>10}{'날짜':>8}")
    for h in HOLDS:
        xs = [r[h] - bench[h][r["date"]]
              for r in rows
              if r.get(h) is not None and r["date"] in bench[h]]
        s = stats(xs)
        if not s:
            continue
        ds = by_date(rows, bench, h)
        print(f"{str(h)+'일':>5}{s['n']:>8,}{s['avg']*100:>+9.2f}%"
              f"{nw_t(ds, h):>8.2f}{s['win']*100:>7.1f}%{s['median']*100:>+9.2f}%"
              f"{(s['avg']-TC_ROUNDTRIP)*100:>+9.2f}%{len(ds):>8,}")

    print(f"\n기간 분리 (train <= {TRAIN_END_DATE} / test 이후)")
    for h in HOLDS:
        line = f"  {str(h)+'일':>5}  "
        for lab, lo, hi in (("train", "", TRAIN_END_DATE), ("test", TRAIN_END_DATE, "")):
            ds = by_date(rows, bench, h, lo, hi)
            if len(ds) < 10:
                line += f"{lab} 표본부족   "
                continue
            avg = sum(ds) / len(ds)
            line += f"{lab} {avg*100:+.2f}% t={nw_t(ds, h):+.2f} ({len(ds):,}일)   "
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
