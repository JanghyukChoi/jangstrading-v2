"""
저위험 이상현상 3종을 반증한다 — 같은 것인가, 사이즈인가, 진짜인가.

1차에서 순열검정을 통과한 것 (60일 보유, 유니버스 시총 1,000억+)
  VOL252   -4.15%  t=-2.66  p=0.020
  MAX21    -3.31%  t=-2.56  p=0.025
  TURN252  -3.67%  t=-2.42  p=0.040

**셋을 세 개의 발견으로 세면 안 된다.** 고변동성·고회전율·복권형은 전부
"투기적 종목"의 대리변수다. 문헌에서도 MAX 가 IVOL 을 흡수한다고 본다
(Bali, Cakici & Whitelaw 2011). 상관이 높으면 이건 **하나의 발견**이고,
다중검정 계산도 달라진다(3회가 아니라 사실상 1회).

그리고 사이즈를 통제하지 않았다. 소형주는 원래 변동성이 크다. 통제 후
사라지면 "저변동성 효과"가 아니라 **대형주 효과**를 다시 발견한 것이다.
연기금 검정에서 같은 함정을 통과시켰던 것과 같은 규율을 적용한다.

검정
  A. 세 팩터의 횡단면 순위상관 — 하나인가 셋인가
  B. 사이즈 3분위 내 비교 — 규모가 설명하는가
  C. 이중정렬 (사이즈 x 변동성) — 대형/소형 양쪽에서 다 나타나는가
  D. 유동성 필터 — 거래가 안 되는 종목이 만든 것은 아닌가
  E. 연도별 — 특정 국면 전용인가

실행
  python scripts/backtest_lowrisk.py --panel <panel.npz>
"""

import argparse
import sys
from collections import defaultdict

import numpy as np

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

MIN_MCAP = 1e11
REBAL, H = 20, 60
SPLIT = "2021-06-30"


def nw_tstat(x, lag):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 15:
        return np.nan, np.nan
    mu = x.mean()
    e = x - mu
    s = float(e @ e) / n
    for L in range(1, min(int(lag), n - 1) + 1):
        s += 2.0 * (1.0 - L / (lag + 1.0)) * float(e[L:] @ e[:-L]) / n
    return (mu, mu / np.sqrt(s / n)) if s > 0 else (mu, np.nan)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", required=True)
    args = ap.parse_args()

    z = np.load(args.panel, allow_pickle=True)
    dates = np.array([str(d) for d in z["dates"]])
    price = z["price"].astype(np.float64)
    mcap = z["mcap"].astype(np.float64)
    turn = z["turn"].astype(np.float64)
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

    rr = np.nan_to_num(r, nan=0.0)
    valid = np.isfinite(r).astype(np.float64)

    def roll_mean(x, w):
        cc = np.cumsum(x, axis=0)
        o = np.full_like(x, np.nan)
        o[w:] = (cc[w:] - cc[:-w]) / w
        return o

    m1, m2 = roll_mean(rr, 252), roll_mean(rr ** 2, 252)
    with np.errstate(invalid="ignore"):
        VOL = np.sqrt(np.maximum(m2 - m1 ** 2, 0)) * np.sqrt(252)
    VOL[roll_mean(valid, 252) < 0.8] = np.nan
    TURNF = roll_mean(np.nan_to_num(turn, nan=0.0), 252)
    MAX21 = np.full((T, N), np.nan)
    for t in range(21, T):
        with np.errstate(invalid="ignore"):
            sl = r[t - 20:t + 1]
            MAX21[t] = np.where(np.isfinite(sl).any(axis=0),
                                np.nanmax(np.where(np.isfinite(sl), sl, -np.inf), axis=0),
                                np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        SIZE = np.where(mcap > 0, np.log(mcap), np.nan)

    FAC = [("VOL252", VOL), ("MAX21", MAX21), ("TURN252", TURNF)]
    rebal = [t for t in range(252, T - H - 1) if t % REBAL == 0]
    print(f"유니버스 시총 {MIN_MCAP/1e8:,.0f}억+ = 일평균 {univ.sum(axis=1).mean():.0f}종목")
    print(f"리밸런스 {len(rebal)}회 ({dates[rebal[0]]} ~ {dates[rebal[-1]]}), {H}일 보유\n")

    def rank01(x, m):
        o = np.full(x.shape, np.nan)
        v = x[m]
        if v.size < 10:
            return o
        o[m] = (np.argsort(np.argsort(v)) + 0.5) / v.size
        return o

    # ── A. 상관 ──────────────────────────────────────────────────
    print("=" * 74)
    print("A. 세 팩터가 같은 것인가 — 횡단면 순위상관 (리밸런스일 평균)")
    print("=" * 74)
    cors = defaultdict(list)
    for t in rebal:
        m = univ[t]
        rk = {n: rank01(s[t], m & np.isfinite(s[t])) for n, s in FAC}
        rk["SIZE"] = rank01(SIZE[t], m & np.isfinite(SIZE[t]))
        keys = list(rk)
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                a, b = rk[keys[i]], rk[keys[j]]
                g = np.isfinite(a) & np.isfinite(b)
                if g.sum() > 50:
                    cors[(keys[i], keys[j])].append(np.corrcoef(a[g], b[g])[0, 1])
    for (a, b), v in cors.items():
        print(f"  {a:9s} x {b:9s}  {np.mean(v):+.2f}")

    # ── B/C. 사이즈 통제 ─────────────────────────────────────────
    def longshort(sig, control=None, univ_extra=None):
        out = []
        for t in rebal:
            m = univ[t] & np.isfinite(f[t]) & np.isfinite(sig[t])
            if univ_extra is not None:
                m &= univ_extra[t]
            idx = np.where(m)[0]
            if len(idx) < 100:
                continue
            s, rv = sig[t][idx], f[t][idx]
            hi = np.zeros(len(s), bool)
            lo = np.zeros(len(s), bool)
            if control is None:
                groups = [np.ones(len(s), bool)]
            else:
                cl = control[t][idx]
                groups = [cl == g for g in (0, 1, 2)]
            for gm in groups:
                if gm.sum() < 30:
                    continue
                q = np.quantile(s[gm], [0.1, 0.9])
                pos = np.where(gm)[0]
                hi[pos[s[gm] >= q[1]]] = True
                lo[pos[s[gm] <= q[0]]] = True
            if hi.sum() < 5 or lo.sum() < 5:
                continue
            out.append(rv[hi].mean() - rv[lo].mean())
        return np.array(out)

    size_lab = np.full((T, N), -1, dtype=np.int8)
    for t in rebal:
        m = univ[t] & np.isfinite(SIZE[t])
        v = SIZE[t][m]
        if v.size >= 30:
            size_lab[t][m] = np.digitize(v, np.quantile(v, [1 / 3, 2 / 3]))

    print("\n" + "=" * 74)
    print("B. 사이즈 통제 — 같은 규모끼리만 비교하면 남는가")
    print("=" * 74)
    print(f"{'팩터':10s}{'통제없음':>18s}{'사이즈 3분위 내':>22s}")
    for name, sig in FAC:
        a = nw_tstat(longshort(sig), 3)
        b = nw_tstat(longshort(sig, control=size_lab), 3)
        print(f"{name:10s}{f'{a[0]*100:+.2f}% t={a[1]:+.2f}':>18s}"
              f"{f'{b[0]*100:+.2f}% t={b[1]:+.2f}':>22s}")

    print("\n" + "=" * 74)
    print("C. 이중정렬 — 대형·중형·소형 각각에서 VOL252 상위10%-하위10%")
    print("=" * 74)
    for gi, glab in ((2, "대형"), (1, "중형"), (0, "소형")):
        sub = (size_lab == gi)
        v = nw_tstat(longshort(VOL, univ_extra=sub), 3)
        print(f"  {glab}  {v[0]*100:+.2f}%  t={v[1]:+.2f}")

    print("\n" + "=" * 74)
    print("D. 유동성 필터 — 일평균 거래대금 하위 30% 제외하면")
    print("=" * 74)
    liq = np.zeros((T, N), dtype=bool)
    tv = roll_mean(np.nan_to_num(turn, nan=0.0) * np.nan_to_num(mcap, nan=0.0), 60)
    for t in rebal:
        m = univ[t] & np.isfinite(tv[t])
        v = tv[t][m]
        if v.size >= 30:
            liq[t][m] = v >= np.quantile(v, 0.3)
    for name, sig in FAC:
        a = nw_tstat(longshort(sig, univ_extra=liq), 3)
        print(f"  {name:10s} {a[0]*100:+.2f}%  t={a[1]:+.2f}")

    print("\n" + "=" * 74)
    print("E. 연도별 — VOL252 상위10%-하위10%")
    print("=" * 74)
    by_year = defaultdict(list)
    for t in rebal:
        m = univ[t] & np.isfinite(f[t]) & np.isfinite(VOL[t])
        idx = np.where(m)[0]
        if len(idx) < 100:
            continue
        s, rv = VOL[t][idx], f[t][idx]
        q = np.quantile(s, [0.1, 0.9])
        hi, lo = s >= q[1], s <= q[0]
        if hi.sum() < 5 or lo.sum() < 5:
            continue
        by_year[dates[t][:4]].append(rv[hi].mean() - rv[lo].mean())
    neg = 0
    for y in sorted(by_year):
        v = np.array(by_year[y])
        neg += v.mean() < 0
        print(f"  {y}  {v.mean()*100:>+7.2f}%  ({len(v)}회 리밸런스)")
    print(f"\n  {len(by_year)}개 연도 중 {neg}개에서 음수(저변동성 우위)")

    print("\n" + "=" * 74)
    print(f"전·후반 (기준 {SPLIT})")
    print("=" * 74)
    first = dates <= SPLIT
    for name, sig in FAC:
        out = []
        for lab, sel in (("전반", first), ("후반", ~first)):
            mask = np.zeros((T, N), bool)
            mask[sel] = True
            v = nw_tstat(longshort(sig, univ_extra=mask), 3)
            out.append(f"{lab} {v[0]*100:+.2f}% t={v[1]:+.2f}")
        print(f"  {name:10s}" + "   ".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
