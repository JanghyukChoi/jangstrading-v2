"""
10년 시계열을 백테스트용 패널(numpy)로 만든다. 핵심은 **액면분할 보정**이다.

scripts/backtest_data/timeseries/*.json 의 prices 는 수정주가가 아니다.
삼성전자는 2018-05-04 에 2,650,000 -> 51,900 으로 찍힌다(50:1 분할).
그대로 수익률을 내면 그날 -98% 다. 전 종목의 33.8%(1,095종목, 1,842건)가
같은 상태라 보정 없이는 어떤 백테스트도 의미가 없다.

보정 근거: **시가총액은 분할 때 연속이다**(331조 -> 333조). 그래서

    주식수 n_t = 시가총액_t / 주가_t
    가격비 r_p = P_t / P_{t-1},  주식수비 r_n = n_t / n_{t-1}

한국 주식은 일일 가격제한이 ±30% 라 r_p 가 [0.65, 1.40] 밖이면 정상 등락이
아니다. 그때 r_p x r_n 이 다시 [0.65, 1.40] 안에 들어오면 주식수 변화가 그
점프를 설명한 것이므로 분할/병합/감자로 보고 k = r_n 으로 과거 가격을 나눈다.
설명되지 않으면 그날 수익률을 결측 처리한다(거래정지 후 재개, 데이터 오류).

자기검증형 규칙이라 임계값을 만질 여지가 없다 — ±30% 는 시장 규칙이지
튜닝 파라미터가 아니다.

출력: scratchpad/panel.npz  (dates, tickers, price_adj, mcap, turnover, ok)

실행: python scripts/backtest_panel.py --out <경로>
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

TS = Path(__file__).resolve().parent / "backtest_data" / "timeseries"

# 한국 일일 가격제한 ±30%. 여유를 둬서 [0.65, 1.40].
LIMIT_LO, LIMIT_HI = 0.65, 1.40


def adjust(prices, mcaps):
    """분할 보정된 가격과, 수익률을 믿을 수 있는 날 마스크를 돌려준다."""
    n = len(prices)
    p = np.asarray(prices, dtype=np.float64)
    m = np.asarray(mcaps, dtype=np.float64)
    ok = np.ones(n, dtype=bool)          # 그날의 수익률(t-1 -> t)을 쓸 수 있는가
    ok[0] = False
    factor = np.ones(n, dtype=np.float64)  # 과거 가격에 곱할 누적 계수

    shares = np.where(p > 0, m / np.where(p > 0, p, 1), 0.0)
    splits = []
    for t in range(1, n):
        if p[t] <= 0 or p[t - 1] <= 0:
            ok[t] = False
            continue
        rp = p[t] / p[t - 1]
        if LIMIT_LO <= rp <= LIMIT_HI:
            continue
        rn = shares[t] / shares[t - 1] if shares[t - 1] > 0 else 0.0
        if rn > 0 and LIMIT_LO <= rp * rn <= LIMIT_HI:
            splits.append((t, rn))       # 주식수 변화가 점프를 설명 -> 분할/병합
        else:
            ok[t] = False                # 설명 안 됨 -> 그날 수익률은 버린다

    # t 이후에 일어난 분할들의 역수 누적 = t 시점 가격을 현재 스케일로 옮기는 계수
    for t0, k in reversed(splits):
        factor[:t0] /= k
    return p * factor, ok, len(splits)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    files = sorted(TS.glob("*.json"))
    print(f"시계열 {len(files)}개 로드")
    t0 = time.monotonic()

    raw = {}
    all_dates = set()
    for i, f in enumerate(files):
        d = json.loads(f.read_text(encoding="utf-8"))
        if not d.get("dates"):
            continue
        raw[f.stem] = d
        all_dates.update(d["dates"])
        if (i + 1) % 800 == 0:
            print(f"  {i+1}/{len(files)}  {time.monotonic()-t0:.0f}초")

    dates = np.array(sorted(all_dates))
    idx = {d: i for i, d in enumerate(dates)}
    tickers = np.array(sorted(raw))
    T, N = len(dates), len(tickers)
    print(f"패널 {T}일 x {N}종목")

    price = np.full((T, N), np.nan, dtype=np.float32)
    mcap = np.full((T, N), np.nan, dtype=np.float32)
    turn = np.full((T, N), np.nan, dtype=np.float32)
    ok = np.zeros((T, N), dtype=bool)

    nsplit = 0
    for j, tk in enumerate(tickers):
        d = raw[tk]
        rows = np.array([idx[x] for x in d["dates"]])
        padj, okv, ns = adjust(d["prices"], d["market_cap"])
        nsplit += ns
        mc = np.asarray(d["market_cap"], dtype=np.float64)
        tv = np.asarray(d["trade_value"], dtype=np.float64)
        # 회전율 = 거래대금 / 시가총액. 거래량·상장주식수를 따로 안 써도 같은 값이다
        # (둘 다 주가로 나뉘어 약분된다). Grinblatt & Han 의 s_t 가 이것이다.
        with np.errstate(divide="ignore", invalid="ignore"):
            s = np.where(mc > 0, tv / mc, np.nan)
        price[rows, j] = padj
        mcap[rows, j] = mc
        turn[rows, j] = np.clip(s, 0, 1)
        ok[rows, j] = okv

    np.savez_compressed(args.out, dates=dates, tickers=tickers,
                        price=price, mcap=mcap, turn=turn, ok=ok)
    print(f"분할 보정 {nsplit}건")
    print(f"수익률 결측 처리된 날: {int((~ok).sum() - (np.isnan(price)).sum()):,}건")
    print(f"저장 {args.out}  ({Path(args.out).stat().st_size/1024/1024:.0f}MB, "
          f"{time.monotonic()-t0:.0f}초)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
