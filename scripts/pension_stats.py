"""
연기금 쏠림 지표를 화면에 올리기 위한 **정직한 통계**를 뽑는다.

평균만 쓰면 안 된다. 원장이 기타법인 생존 팩터에 대해 남긴 경고가 그대로
적용된다 — "승률 45.3%, 중앙값 음수 → 포트폴리오 틸트로만 유효, 개별 알림
부적합". 평균 -0.87% 를 "이 종목은 떨어집니다"로 읽히게 두면 거짓말이 된다.

그래서 화면에 같이 실을 수치를 여기서 전부 만든다.
  - 10분위 표      단조성을 눈으로 보여주는 것이 평균 한 줄보다 정직하다
  - 승률           몇 %의 경우에 실제로 언더퍼폼했나
  - 중앙값         평균이 소수 극단값에 끌려간 것은 아닌가
  - 연도별         특정 국면에만 나온 것은 아닌가
  - 분포           최악·최선 구간

지표 정의는 검정한 것과 **정확히 같아야 한다**
  연기금 120영업일 누적 순매수 / 시가총액, 상위 10%, 60영업일 보유.
  사이트의 pension["6m"] 이 PERIODS 상 120영업일이라 그대로 쓸 수 있다.

실행
  python scripts/pension_stats.py --panel <panel.npz>
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

BASE = Path(__file__).resolve().parent.parent
SNAPS = BASE / "scripts" / "backtest_data" / "snapshots"
MIN_MCAP = 5e11
W, H = 120, 60


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", required=True)
    args = ap.parse_args()

    z = np.load(args.panel, allow_pickle=True)
    dates = np.array([str(d) for d in z["dates"]])
    tickers = [str(t) for t in z["tickers"]]
    price = z["price"].astype(np.float64)
    mcap = z["mcap"].astype(np.float64)
    T, N = price.shape

    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.full((T, N), np.nan)
        r[1:] = price[1:] / price[:-1] - 1.0
    r[~z["ok"]] = np.nan
    r[np.abs(r) > 0.45] = np.nan
    univ = (mcap >= MIN_MCAP) & np.isfinite(price) & (price > 0)
    mkt = np.nanmean(np.where(univ[:-1], r[1:], np.nan), axis=1)
    exc = np.full((T, N), np.nan)
    exc[1:] = r[1:] - mkt[:, None]

    c = np.nancumsum(np.nan_to_num(exc, nan=0.0), axis=0)
    cv = np.cumsum(np.isfinite(exc).astype(np.int32), axis=0)
    f = np.full((T, N), np.nan)
    for t in range(0, T - H - 1):
        f[t] = c[t + H] - c[t]
        f[t][(cv[t + H] - cv[t]) < H] = np.nan

    tidx = {t: i for i, t in enumerate(tickers)}
    flow = np.zeros((T, N), dtype=np.float32)
    for i, d in enumerate(dates):
        p = SNAPS / f"{d}.json"
        if not p.exists():
            continue
        try:
            snap = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for tk, v in (snap.get("pension_1d") or {}).items():
            j = tidx.get(tk)
            if j is not None and isinstance(v, (int, float)):
                flow[i, j] = v

    cum = np.cumsum(flow.astype(np.float64), axis=0)
    sig = np.full((T, N), np.nan)
    sig[W:] = (cum[W:] - cum[:-W]) * 1e6 / np.where(mcap[W:] > 0, mcap[W:], np.nan)

    # 종목-사건 단위로 모은다. 날짜별 평균이 아니라 **개별 종목의 결과**가
    # 화면에서 필요한 값이다 — 사용자는 종목 하나를 보고 있다.
    dec_rows = defaultdict(list)
    top_events, bot_events = [], []
    by_year = defaultdict(list)
    daily_top = []

    for t in range(W, T - H - 1):
        m = univ[t] & np.isfinite(sig[t]) & np.isfinite(f[t])
        if m.sum() < 100:
            continue
        s, rr = sig[t][m], f[t][m]
        edges = np.quantile(s, np.linspace(0, 1, 11))
        idx = np.clip(np.searchsorted(edges, s, side="right") - 1, 0, 9)
        base = rr.mean()
        for d in range(10):
            sel = idx == d
            if sel.any():
                dec_rows[d].append(rr[sel].mean() - base)
        hi, lo = idx == 9, idx == 0
        if hi.sum() >= 5:
            top_events.extend((rr[hi] - base).tolist())
            daily_top.append(rr[hi].mean() - base)
            by_year[dates[t][:4]].append(rr[hi].mean() - base)
        if lo.sum() >= 5:
            bot_events.extend((rr[lo] - base).tolist())

    print(f"검정 기간 {dates[W]} ~ {dates[T-H-2]}  ({len(daily_top):,}일)")
    print(f"지표: 연기금 {W}영업일 누적 순매수 / 시가총액, {H}영업일 보유\n")

    print("=" * 66)
    print("10분위별 이후 60일 초과수익 (종목-사건 평균)")
    print("=" * 66)
    for d in range(10):
        v = np.array(dec_rows[d])
        bar = "█" * max(0, int(round(abs(v.mean()) * 100 * 6)))
        tag = "  <- 연기금 최다 매수" if d == 9 else ("  <- 연기금 최다 매도" if d == 0 else "")
        print(f"  {d+1:>2}분위  {v.mean()*100:>+7.2f}%  {bar}{tag}")
    dm = np.array([np.mean(dec_rows[d]) for d in range(10)])
    print(f"\n  단조성(순위-수익 상관) rho = {np.corrcoef(np.arange(10), dm)[0,1]:+.2f}")

    print("\n" + "=" * 66)
    print("상위 10% (연기금 집중 매수) — 개별 종목-사건 기준")
    print("=" * 66)
    te = np.array(top_events)
    be = np.array(bot_events)
    print(f"  관측 종목-사건    {len(te):,}건")
    print(f"  평균 초과수익     {te.mean()*100:+.2f}%")
    print(f"  중앙값            {np.median(te)*100:+.2f}%")
    print(f"  언더퍼폼 비율     {(te < 0).mean()*100:.1f}%   <- 이게 '승률'이다")
    print(f"  하위 25% / 상위 25%  {np.percentile(te,25)*100:+.1f}% / "
          f"{np.percentile(te,75)*100:+.1f}%")
    print(f"\n  (대조) 하위 10% 평균 {be.mean()*100:+.2f}%  "
          f"중앙값 {np.median(be)*100:+.2f}%  "
          f"아웃퍼폼 비율 {(be > 0).mean()*100:.1f}%")

    print("\n" + "=" * 66)
    print("연도별 — 상위 10% 의 일평균 초과수익")
    print("=" * 66)
    neg = 0
    for y in sorted(by_year):
        v = np.array(by_year[y])
        if len(v) < 20:
            continue
        neg += v.mean() < 0
        mark = "음(예측대로)" if v.mean() < 0 else "양(반대)"
        print(f"  {y}  {v.mean()*100:>+7.2f}%   {mark}")
    yrs = [y for y in sorted(by_year) if len(by_year[y]) >= 20]
    print(f"\n  {len(yrs)}개 연도 중 {neg}개에서 음수")

    print("\n" + "=" * 66)
    print("화면에 쓸 문구 (이대로 쓰면 과장이 없다)")
    print("=" * 66)
    print(f"  연기금이 최근 120거래일간 시가총액 대비 많이 담은 상위 10% 종목은")
    print(f"  이후 60거래일 동안 시장 대비 평균 {te.mean()*100:+.2f}%,")
    print(f"  중앙값 {np.median(te)*100:+.2f}% 의 성과를 냈습니다.")
    print(f"  {(te < 0).mean()*100:.0f}% 의 경우에 시장을 밑돌았습니다 "
          f"(= {100-(te<0).mean()*100:.0f}% 는 그렇지 않았습니다).")
    print(f"  2016년 이후 {len(yrs)}개 연도 중 {neg}개 연도에서 이 방향이 나타났습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
