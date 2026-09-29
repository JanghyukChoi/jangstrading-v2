"""
장기 팩터 검정 — 수급이 아니라 **가격·규모·거래량**에서 나오는 것들.

왜 방향을 바꾸는가
  지금까지 검정한 건 전부 수급이고 지평이 1~60일이었다. 전멸했다.
  그런데 자산가격론에서 가장 많이 복제된 결과들은 수급이 아니라 가격 특성이고,
  지평이 **월~년**이다. 공간이 다르므로 다시 물어볼 가치가 있다.

무엇을 검정할 수 있고 없는가 — 먼저 정직하게
  검정 **불가**: 가치(B/M, E/P), 퀄리티(ROE, GP/A), 성장.
    과거 PER/PBR/EPS 가 없다. 현재 스냅샷만 있다. 이게 뼈아프다 —
    장기 증거가 가장 두꺼운 영역이 통째로 빠진다.
  검정 **가능**: 가격·시총·거래대금에서 만드는 것들. 아래 6종.

검정 대상 (전부 횡단면 z-score, 월 1회 리밸런스)
  VOL252    252일 일간수익률 표준편차        저변동성 이상현상
  TURN252   (거래대금/시총) 252일 평균       저회전율·유동성
  SIZE      log 시가총액                     소형주 효과
  REV36     과거 36개월 수익률               장기반전 (DeBondt-Thaler 1985)
  MOM12_1   과거 252일 수익률 (최근 21일 제외) 모멘텀 — **대조군**
  MAX21     최근 21일 중 최대 일간수익률      복권형 선호 (Bali et al. 2011)

대조군이 중요하다. 원장에 "한국 모멘텀 상위 30종목 매수는 항상 지는 전략"이
적혀 있다. MOM12_1 이 그 방향으로 나오면 검정 파이프라인이 정상이라는 뜻이고,
반대로 나오면 파이프라인을 의심해야 한다.

규율 (앞선 검정과 동일)
  - 초과수익: 그날 유니버스 동일가중 평균 차감
  - 월 1회 리밸런스로 중첩을 줄이고, 남은 중첩은 Newey-West 로 보정
  - 종목 라벨 순열 200회 (전 기간 동일 치환)
  - 격자 전체 보고. 좋은 칸만 고르지 않는다.

한계 (미리 적는다)
  10.3년이다. 12개월 보유면 독립 구간이 10개뿐이다. 유의하지 않게 나와도
  "효과 없음"이 아니라 "이 표본으로는 모른다"일 수 있다.

실행
  python scripts/backtest_longfactors.py --panel <panel.npz> --draws 200
"""

import argparse
import sys

import numpy as np

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

MIN_MCAP = 1e11        # 1,000억. 횡단면 종목수를 늘려 분위 평균의 노이즈를 줄인다
REBAL = 20            # 월 1회
HORIZONS = (20, 60, 252)
LOOKBACK = 252        # 팩터마다 가용 구간이 다르다. REV36 는 756일 전까지
                      # NaN 이라 longshort() 가 알아서 건너뛴다. 공통 하한을
                      # 756 으로 잡으면 나머지 5개 팩터가 3년치를 손해본다.
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
    ap.add_argument("--draws", type=int, default=200)
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

    def fwd(h):
        c = np.nancumsum(np.nan_to_num(exc, nan=0.0), axis=0)
        cv = np.cumsum(np.isfinite(exc).astype(np.int32), axis=0)
        o = np.full((T, N), np.nan)
        for t in range(0, T - h - 1):
            o[t] = c[t + h] - c[t]
            o[t][(cv[t + h] - cv[t]) < h] = np.nan
        return o

    FWD = {h: fwd(h) for h in HORIZONS}
    print(f"패널 {T}일 x {N}종목 ({dates[0]} ~ {dates[-1]})")
    print(f"유니버스 시총 {MIN_MCAP/1e8:,.0f}억 이상 = 일평균 {univ.sum(axis=1).mean():.0f}종목")

    # ── 팩터 ────────────────────────────────────────────────────────
    print("팩터 계산 중...", flush=True)
    rr = np.nan_to_num(r, nan=0.0)
    valid = np.isfinite(r).astype(np.float64)

    def roll_mean(x, w):
        c = np.cumsum(x, axis=0)
        o = np.full_like(x, np.nan)
        o[w:] = (c[w:] - c[:-w]) / w
        return o

    m1 = roll_mean(rr, 252)
    m2 = roll_mean(rr ** 2, 252)
    with np.errstate(invalid="ignore"):
        VOL252 = np.sqrt(np.maximum(m2 - m1 ** 2, 0)) * np.sqrt(252)
    VOL252[roll_mean(valid, 252) < 0.8] = np.nan

    TURN252 = roll_mean(np.nan_to_num(turn, nan=0.0), 252)

    with np.errstate(invalid="ignore", divide="ignore"):
        SIZE = np.where(mcap > 0, np.log(mcap), np.nan)

    def past_ret(w, skip=0):
        o = np.full((T, N), np.nan)
        a, b = w + skip, skip
        if b == 0:
            o[a:] = price[a:] / price[:-a] - 1.0
        else:
            o[a:] = price[a - b:T - b] / price[:T - a] - 1.0
        return o

    REV36 = past_ret(756)
    MOM12_1 = past_ret(231, skip=21)

    MAX21 = np.full((T, N), np.nan)
    for t in range(21, T):
        MAX21[t] = np.nanmax(r[t - 20:t + 1], axis=0)

    FACTORS = [
        ("VOL252", VOL252, "저변동성이면 음의 값이 좋다"),
        ("TURN252", TURN252, "저회전율이면 음"),
        ("SIZE", SIZE, "소형주 효과면 음"),
        ("REV36", REV36, "장기반전이면 음"),
        ("MOM12_1", MOM12_1, "대조군 — 한국은 음이어야 정상"),
        ("MAX21", MAX21, "복권형 회피면 음"),
    ]

    rebal = [t for t in range(LOOKBACK, T - max(HORIZONS) - 1) if t % REBAL == 0]
    print(f"리밸런스 {len(rebal)}회 ({dates[rebal[0]]} ~ {dates[rebal[-1]]})\n")

    def longshort(sig, h, sel=None, perm=None):
        f = FWD[h]
        out, used = [], []
        for t in rebal:
            if sel is not None and not sel[t]:
                continue
            m = univ[t] & np.isfinite(f[t])
            idx = np.where(m)[0]
            s = sig[t][idx if perm is None else perm[idx]]
            good = np.isfinite(s)
            if good.sum() < 100:
                continue
            s2, r2 = s[good], f[t][idx[good]]
            q = np.quantile(s2, [0.1, 0.9])
            hi, lo = s2 >= q[1], s2 <= q[0]
            if hi.sum() < 5 or lo.sum() < 5:
                continue
            out.append(r2[hi].mean() - r2[lo].mean())
            used.append(t)
        return np.array(out), np.array(used)

    print("=" * 80)
    print("상위10% - 하위10% 초과수익 (%) · 월 1회 리밸런스 · 발표 다음날 진입")
    print("=" * 80)
    print(f"{'팩터':10s}" + "".join(f"{h:>10d}일" for h in HORIZONS) + f"{'  단조성':>10s}  해석")
    results = {}
    for name, sig, note in FACTORS:
        line = f"{name:10s}"
        tline = " " * 10
        rhos = []
        for h in HORIZONS:
            ls, _ = longshort(sig, h)
            mu, tt = nw_tstat(ls, max(1, h // REBAL))
            results[(name, h)] = (mu, tt, ls)
            line += f"{mu*100:>+10.2f}{'*' if abs(tt) >= 2 else ' '}"
            tline += f"{tt:>11.2f}"
        # 단조성은 60일 기준
        f60 = FWD[60]
        dm_s, dm_c = np.zeros(10), np.zeros(10)
        for t in rebal:
            m = univ[t] & np.isfinite(sig[t]) & np.isfinite(f60[t])
            if m.sum() < 100:
                continue
            s, rv = sig[t][m], f60[t][m]
            e = np.quantile(s, np.linspace(0, 1, 11))
            di = np.clip(np.searchsorted(e, s, side="right") - 1, 0, 9)
            for d in range(10):
                q = di == d
                if q.any():
                    dm_s[d] += rv[q].mean()
                    dm_c[d] += 1
        with np.errstate(invalid="ignore"):
            dm = dm_s / np.where(dm_c > 0, dm_c, np.nan)
        rho = np.corrcoef(np.arange(10), dm)[0, 1] if np.isfinite(dm).all() else np.nan
        print(line + f"{rho:>10.2f}   {note}")
        print(tline)
    print("\n  * = |t| >= 2.0 (Newey-West).  단조성은 60일 기준.")

    # ── 순열검정: 60일·252일에서 유의한 것만 ────────────────────────
    cands = [(n, h) for (n, h), (mu, tt, _) in results.items()
             if h in (60, 252) and abs(tt) >= 2.0]
    print("\n" + "=" * 80)
    print(f"순열검정 {args.draws}회 — 60일·252일에서 |t|>=2 인 칸만")
    print("=" * 80)
    if not cands:
        print("  해당 없음. 장기 지평에서 유의한 팩터가 없다.")
    rng = np.random.default_rng(20260929)
    sigmap = {n: s for n, s, _ in FACTORS}
    for name, h in sorted(cands):
        mu, t0, _ = results[(name, h)]
        null_t = []
        for _ in range(args.draws):
            perm = rng.permutation(N)
            ls, _ = longshort(sigmap[name], h, perm=perm)
            _, tt = nw_tstat(ls, max(1, h // REBAL))
            if np.isfinite(tt):
                null_t.append(tt)
        null_t = np.array(null_t)
        p = float((np.abs(null_t) >= abs(t0)).mean())
        print(f"  {name:10s} {h:>3d}일  실제 {mu*100:+.2f}% t={t0:+.2f}  "
              f"귀무 표준편차 {null_t.std():.2f}  p={p:.3f}  "
              f"{'생존' if p < 0.05 else '기각'}")

    # ── 전·후반 ─────────────────────────────────────────────────────
    print("\n" + "=" * 80)
    print(f"전·후반 분리 (기준 {SPLIT}) — 60일 보유")
    print("=" * 80)
    first = dates <= SPLIT
    for name, sig, _ in FACTORS:
        out = []
        for lab, sel in (("전반", first), ("후반", ~first)):
            ls, _ = longshort(sig, 60, sel=sel)
            mu, tt = nw_tstat(ls, 3)
            out.append(f"{lab} {mu*100:+.2f}% t={tt:+.2f}")
        print(f"  {name:10s}" + "   ".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
