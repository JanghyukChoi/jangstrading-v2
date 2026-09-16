"""
backtest_cgo.py 의 [4] 결과(모멘텀 하위권에서 CGO 역방향, t=-5.69)를 흔들어 본다.

의심하는 이유: 모멘텀 하위 + CGO 하위는 크게 빠진 종목이고, 상장폐지가 가장
많이 나오는 구간이다. 본 백테스트는 폐지 시 '마지막 거래가격'으로 청산하는데
정리매매에서 더 빠지는 몫이 빠져 있다. 그러면 CGO 하위 수익률이 과대평가되고
-2.67% 라는 격차가 통째로 그 편향일 수 있다.

네 가지를 바꿔가며 같은 수를 다시 낸다. 하나라도 뒤집히면 쓰면 안 되는 결과다.

  1) 폐지 처리   마지막 가격 청산 vs -100% 상각
  2) 가중        동일가중 vs 시총가중
  3) 규모        전체 vs 하위 30% 제외
  4) 유동성      전체 vs 회전율 상위 20% 제외

실행: python scripts/backtest_cgo_robust.py --panel <panel.npz>
"""

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from backtest_cgo import (  # noqa: E402
    MAX_INIT_W, MIN_DAYS, MIN_PRICE, MOM_LEN, MOM_SKIP, N_GROUPS,
    compute_cgo, month_ends, nw_tstat, qgroups, wmean,
)


def fwd_return(price, ok, i0, i1, delist_zero):
    """delist_zero=True 면 보유기간 중 가격이 끊긴 종목을 -100% 로 본다."""
    T, N = price.shape
    e = min(i0 + 1, T - 1)
    x = min(i1 + 1, T - 1)
    entry = price[e].astype(np.float64)
    seg = price[e:x + 1]
    okseg = ok[e + 1:x + 1]

    fin = np.isfinite(seg)
    has = fin.any(axis=0)
    idx_last = np.where(has, fin.shape[0] - 1 - np.argmax(fin[::-1], axis=0), -1)
    last = np.full(N, np.nan)
    for j in np.where(has & np.isfinite(entry) & (entry > 0))[0]:
        k = idx_last[j]
        if okseg.shape[0] and k > 0 and not okseg[:k, j].all():
            continue
        # 만기 전에 가격이 끊겼다 = 상장폐지
        if k < seg.shape[0] - 1 and delist_zero:
            last[j] = 0.0
        else:
            last[j] = seg[k, j]
    with np.errstate(invalid="ignore", divide="ignore"):
        return last / entry - 1


def run(price, mcap, turn, ok, cgo, iw, ndays, common, me, dates,
        delist_zero=False, value_weight=False, drop_small=False, drop_churn=False):
    out = {k: [] for k in range(N_GROUPS)}
    flat = []
    for i0 in me:
        i1 = i0 + 21
        if i1 >= price.shape[0] - 1:
            continue
        c = cgo[i0].astype(np.float64)
        p0 = price[i0].astype(np.float64)
        mc = mcap[i0].astype(np.float64)
        tv = turn[i0].astype(np.float64)
        elig = (common & np.isfinite(c) & np.isfinite(p0) & (p0 >= MIN_PRICE)
                & np.isfinite(mc) & (mc > 0)
                & (ndays[i0] >= MIN_DAYS) & (iw[i0] <= MAX_INIT_W))
        if drop_small and elig.sum() > 100:
            cut = np.nanpercentile(mc[elig], 30)
            elig &= mc >= cut
        if drop_churn and elig.sum() > 100:
            cut = np.nanpercentile(tv[elig & np.isfinite(tv)], 80)
            elig &= np.isfinite(tv) & (tv <= cut)
        if elig.sum() < 200:
            continue

        r1 = fwd_return(price, ok, i0, i1, delist_zero)

        ia, ib = i0 - MOM_SKIP, i0 - MOM_LEN
        if ib < 0:
            continue
        with np.errstate(invalid="ignore", divide="ignore"):
            mom = price[ia].astype(np.float64) / price[ib].astype(np.float64) - 1
        cc = np.where(elig, c, np.nan)
        mg = qgroups(np.where(elig, mom, np.nan), N_GROUPS)
        for k in range(N_GROUPS):
            sub = mg == k
            if sub.sum() < N_GROUPS * 10:
                continue
            cg = qgroups(np.where(sub, cc, np.nan), N_GROUPS)
            if value_weight:
                hi = wmean(r1[cg == N_GROUPS - 1], mc[cg == N_GROUPS - 1])
                lo = wmean(r1[cg == 0], mc[cg == 0])
            else:
                with np.errstate(invalid="ignore"):
                    hi = float(np.nanmean(r1[cg == N_GROUPS - 1]))
                    lo = float(np.nanmean(r1[cg == 0]))
            if np.isfinite(hi) and np.isfinite(lo):
                out[k].append(hi - lo)
        # 전체(모멘텀 무시) CGO 스프레드
        g = qgroups(cc, N_GROUPS)
        if value_weight:
            hi, lo = wmean(r1[g == N_GROUPS - 1], mc[g == N_GROUPS - 1]), wmean(r1[g == 0], mc[g == 0])
        else:
            with np.errstate(invalid="ignore"):
                hi, lo = float(np.nanmean(r1[g == N_GROUPS - 1])), float(np.nanmean(r1[g == 0]))
        if np.isfinite(hi) and np.isfinite(lo):
            flat.append(hi - lo)
    return out, flat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", required=True)
    args = ap.parse_args()

    z = np.load(args.panel, allow_pickle=True)
    dates, tickers = z["dates"], z["tickers"]
    price, mcap, turn, ok = z["price"], z["mcap"], z["turn"], z["ok"]
    T = price.shape[0]
    common = np.array([t[-1] == "0" for t in tickers])
    cgo, iw, ndays = compute_cgo(price, turn)
    me = month_ends(dates)
    me = me[(me >= MIN_DAYS) & (me < T - 25)]

    # 보유 중 상장폐지가 얼마나 나오는지 먼저 센다
    dl = tot = 0
    for i0 in me:
        i1 = i0 + 21
        if i1 >= T - 1:
            continue
        e, x = i0 + 1, min(i1 + 1, T - 1)
        live0 = np.isfinite(price[e]) & common
        alive1 = np.isfinite(price[x])
        dl += int((live0 & ~alive1).sum())
        tot += int(live0.sum())
    print(f"1개월 보유 중 가격이 끊기는 비율: {dl/tot*100:.3f}%  ({dl:,}/{tot:,})\n")

    cases = [
        ("기준 (마지막가격 청산, 동일가중, 전체)", {}),
        ("폐지를 -100% 로 상각",                  {"delist_zero": True}),
        ("시총가중",                              {"value_weight": True}),
        ("소형주 하위 30% 제외",                  {"drop_small": True}),
        ("고회전 상위 20% 제외",                  {"drop_churn": True}),
        ("폐지 -100% + 시총가중 + 소형주 제외",
         {"delist_zero": True, "value_weight": True, "drop_small": True}),
    ]
    print(f"{'조건':<36}{'모멘텀Q1':>12}{'모멘텀Q5':>12}{'평균':>10}{'전체':>10}")
    print("-" * 80)
    for label, kw in cases:
        out, flat = run(price, mcap, turn, ok, cgo, iw, ndays, common, me, dates, **kw)
        q1 = np.array(out[0], float)
        q5 = np.array(out[N_GROUPS - 1], float)
        avg = np.mean([np.nanmean(np.array(out[k], float)) for k in range(N_GROUPS) if out[k]])
        fl = np.array(flat, float)
        print(f"{label:<36}"
              f"{np.nanmean(q1)*100:>+8.2f}%(t{nw_tstat(q1,1):+.1f})"
              f"{np.nanmean(q5)*100:>+8.2f}%(t{nw_tstat(q5,1):+.1f})"
              f"{avg*100:>+9.2f}%{np.nanmean(fl)*100:>+9.2f}%")
    print("\n* 숫자는 CGO Q5-Q1 (주가가 평균단가 위인 그룹 - 아래인 그룹), 1개월 보유")
    return 0


if __name__ == "__main__":
    sys.exit(main())
