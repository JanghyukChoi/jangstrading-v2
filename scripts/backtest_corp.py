"""
기타법인·개인 수급의 예측력 — 외국인·기관과 같은 잣대로.

왜 이 둘인가
  1) 원장에서 KR 수급 152팩터를 재검정했을 때 **생존 6개가 전부 기타법인**이었다.
     외국인·기관 방향성은 188팩터 전멸이었는데 여기만 남았다.
  2) 기타법인은 KRX 분류에서 내부자에 가장 가깝다 — 자사주, 계열사 지분,
     M&A 장내매집. 정보 우위를 가질 **이유**가 있는 유일한 주체다.
  3) 개인은 반대편 대조군이다. 개인이 정말 진다면 부호가 반대로 나와야 한다.
     안 나오면 "개인의 반대편에 알파가 있다"는 통념이 여기서도 깨진다.

앞선 검정(backtest_smartmoney*.py)과 **같은 규칙**을 쓴다. 규칙을 바꾸면
비교가 안 된다.
  - 초과수익(그날 유니버스 동일가중 평균 차감)
  - 발표 다음날 진입
  - Newey-White 중첩보정
  - 사이즈·모멘텀 3분위 내 비교
  - 종목 라벨 순열 200회 (전 기간 동일 치환)

데이터
  scripts/backtest_data/flows/*.json = {YYYYMMDD: [개인, 기타법인]} 백만원
  1,154종목. 시총 상위 1,000종목 중 996개를 덮어 검정 유니버스와 사실상 일치.

실행
  python scripts/backtest_corp.py --panel <panel.npz> --draws 200
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

BASE = Path(__file__).resolve().parent.parent
FLOWS = BASE / "scripts" / "backtest_data" / "flows"

GROUPS = [("개인", 0), ("기타법인", 1)]
WINDOWS = (5, 20, 60, 120)
HORIZONS = (5, 20, 60)
MIN_MCAP = 5e11
FW, FH = 120, 60          # 정밀검정 칸. 원장의 생존 스펙과 같다.
SPLIT = "2021-06-30"


def nw_tstat(x, lag):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 30:
        return np.nan, np.nan
    mu = x.mean()
    e = x - mu
    s = float(e @ e) / n
    for L in range(1, min(int(lag), n - 1) + 1):
        s += 2.0 * (1.0 - L / (lag + 1.0)) * float(e[L:] @ e[:-L]) / n
    return (mu, mu / np.sqrt(s / n)) if s > 0 else (mu, np.nan)


def load_flows(dates, tickers):
    """{YYYYMMDD: [개인, 기타법인]} 파일들을 (T, N) 두 장으로."""
    tidx = {t: i for i, t in enumerate(tickers)}
    didx = {d.replace("-", ""): i for i, d in enumerate(dates)}
    out = [np.zeros((len(dates), len(tickers)), dtype=np.float32) for _ in GROUPS]
    files = [p for p in FLOWS.glob("*.json") if p.stem != "_progress"]
    used = 0
    for p in files:
        j = tidx.get(p.stem)
        if j is None:
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        used += 1
        for ymd, v in d.items():
            i = didx.get(ymd)
            if i is None or not isinstance(v, list) or len(v) < 2:
                continue
            for g, _ in enumerate(GROUPS):
                if isinstance(v[g], (int, float)):
                    out[g][i, j] = v[g]
    return out, used


def tercile(x, m):
    lab = np.full(x.shape, -1, dtype=np.int8)
    v = x[m]
    if v.size < 30:
        return lab
    lab[m] = np.digitize(v, np.quantile(v, [1 / 3, 2 / 3]))
    return lab


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", required=True)
    ap.add_argument("--draws", type=int, default=200)
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

    def fwd(h):
        c = np.nancumsum(np.nan_to_num(exc, nan=0.0), axis=0)
        cv = np.cumsum(np.isfinite(exc).astype(np.int32), axis=0)
        o = np.full((T, N), np.nan)
        for t in range(0, T - h - 1):
            o[t] = c[t + h] - c[t]
            o[t][(cv[t + h] - cv[t]) < h] = np.nan
        return o

    FWD = {h: fwd(h) for h in HORIZONS}
    mom = np.full((T, N), np.nan)
    mom[20:] = FWD[20][:-20]

    flows, used = load_flows(dates, tickers)
    # 수급 파일이 없는 종목은 0 으로 남는다 — 검정에서 빼야 한다.
    have = np.zeros(N, dtype=bool)
    for g in range(len(GROUPS)):
        have |= (flows[g] != 0).any(axis=0)
    univ &= have[None, :]

    print(f"패널 {T}일 x {N}종목 · 수급 보유 {used}종목")
    print(f"유니버스: 시총 {MIN_MCAP/1e8:,.0f}억 이상 & 수급 보유 "
          f"= 일평균 {univ.sum(axis=1).mean():.0f}종목\n")

    sigs = {}
    for gi, (label, _) in enumerate(GROUPS):
        print("=" * 76)
        print(f"{label} 누적순매수/시가총액 — 상위10% - 하위10% 초과수익(%)")
        print("=" * 76)
        print("누적\\보유" + "".join(f"{h:>9d}일" for h in HORIZONS) + f"{'단조성':>9s}")
        cum = np.cumsum(np.nan_to_num(flows[gi], nan=0.0), axis=0)
        for Wd in WINDOWS:
            sig = np.full((T, N), np.nan)
            sig[Wd:] = (cum[Wd:] - cum[:-Wd]) * 1e6 / np.where(mcap[Wd:] > 0, mcap[Wd:], np.nan)
            if Wd == FW:
                sigs[label] = sig
            cells, rhos = [], []
            for h in HORIZONS:
                fh = FWD[h]
                daily = []
                dm_sum, dm_cnt = np.zeros(10), np.zeros(10)
                for t in range(Wd, T - h - 1):
                    m = univ[t] & np.isfinite(sig[t]) & np.isfinite(fh[t])
                    if m.sum() < 80:
                        continue
                    s, rr = sig[t][m], fh[t][m]
                    q = np.quantile(s, [0.1, 0.9])
                    hi, lo = s >= q[1], s <= q[0]
                    if hi.sum() < 5 or lo.sum() < 5:
                        continue
                    daily.append(rr[hi].mean() - rr[lo].mean())
                    e = np.quantile(s, np.linspace(0, 1, 11))
                    idx = np.clip(np.searchsorted(e, s, side="right") - 1, 0, 9)
                    for d in range(10):
                        sel = idx == d
                        if sel.any():
                            dm_sum[d] += rr[sel].mean()
                            dm_cnt[d] += 1
                mu, tt = nw_tstat(daily, max(h, 5))
                cells.append((mu, tt))
                with np.errstate(invalid="ignore"):
                    dm = dm_sum / np.where(dm_cnt > 0, dm_cnt, np.nan)
                if np.isfinite(dm).all():
                    rhos.append(np.corrcoef(np.arange(10), dm)[0, 1])
            line = f"{Wd:>6d}일  "
            for mu, tt in cells:
                line += f"{mu*100:>+8.2f}{'*' if abs(tt) >= 2 else ' '}"
            print(line + f"{np.mean(rhos) if rhos else np.nan:>9.2f}")
            print("        t" + "".join(f"{tt:>9.2f}" for _, tt in cells))
        print()

    # ── 정밀검정: 다리 분해 · 통제 · 순열 ────────────────────────────
    size_lab = np.full((T, N), -1, dtype=np.int8)
    mom_lab = np.full((T, N), -1, dtype=np.int8)
    with np.errstate(invalid="ignore", divide="ignore"):
        logmc = np.where(mcap > 0, np.log(mcap), np.nan)
    for t in range(FW, T - FH - 1):
        size_lab[t] = tercile(logmc[t], univ[t] & np.isfinite(logmc[t]))
        mom_lab[t] = tercile(mom[t], univ[t] & np.isfinite(mom[t]))

    fh = FWD[FH]
    days = []
    for t in range(FW, T - FH - 1):
        m = univ[t] & np.isfinite(fh[t])
        if m.sum() >= 80:
            days.append((t, np.where(m)[0]))

    def legs(sig, control=None, perm=None):
        hi_s, lo_s, ls_s = [], [], []
        for t, idx in days:
            s = sig[t][idx if perm is None else perm[idx]]
            rr = fh[t][idx]
            good = np.isfinite(s)
            if good.sum() < 80:
                continue
            s, rr = s[good], rr[good]
            ii = idx[good]
            base = rr.mean()
            hm = np.zeros(len(s), dtype=bool)
            lm = np.zeros(len(s), dtype=bool)
            groups = [np.ones(len(s), bool)] if control is None else [
                control[t][ii] == g for g in (0, 1, 2)]
            for gm in groups:
                if gm.sum() < 25:
                    continue
                q = np.quantile(s[gm], [0.1, 0.9])
                pos = np.where(gm)[0]
                hm[pos[s[gm] >= q[1]]] = True
                lm[pos[s[gm] <= q[0]]] = True
            if hm.sum() < 5 or lm.sum() < 5:
                continue
            hi_s.append(rr[hm].mean() - base)
            lo_s.append(rr[lm].mean() - base)
            ls_s.append(rr[hm].mean() - rr[lm].mean())
        return hi_s, lo_s, ls_s

    print("=" * 76)
    print(f"정밀검정 — {FW}일 누적 / {FH}일 보유")
    print("=" * 76)
    print(f"{'주체':10s}{'상위10%':>11s}{'t':>7s}{'하위10%':>11s}{'t':>7s}"
          f"{'롱숏':>10s}{'t':>7s}")
    ls_real = {}
    for label, _ in GROUPS:
        hi, lo, ls = legs(sigs[label])
        ls_real[label] = ls
        mh, th = nw_tstat(hi, FH)
        ml, tl = nw_tstat(lo, FH)
        ms, ts = nw_tstat(ls, FH)
        print(f"{label:10s}{mh*100:>10.2f}%{th:>7.2f}{ml*100:>10.2f}%{tl:>7.2f}"
              f"{ms*100:>9.2f}%{ts:>7.2f}")

    print(f"\n{'주체':10s}{'통제없음':>16s}{'사이즈 중립':>18s}{'모멘텀 중립':>18s}")
    for label, _ in GROUPS:
        cells = []
        for ctrl in (None, size_lab, mom_lab):
            _, _, ls = legs(sigs[label], control=ctrl)
            mu, tt = nw_tstat(ls, FH)
            cells.append(f"{mu*100:+.2f}% t={tt:+.2f}")
        print(f"{label:10s}{cells[0]:>16s}{cells[1]:>18s}{cells[2]:>18s}")

    print(f"\n순열검정 {args.draws}회 (종목 라벨 전 기간 동일 치환)")
    rng = np.random.default_rng(20260929)
    for label, _ in GROUPS:
        _, t0 = nw_tstat(ls_real[label], FH)
        null_t = []
        for _ in range(args.draws):
            perm = rng.permutation(N)
            _, _, ls = legs(sigs[label], perm=perm)
            _, tt = nw_tstat(ls, FH)
            if np.isfinite(tt):
                null_t.append(tt)
        null_t = np.array(null_t)
        p = float((np.abs(null_t) >= abs(t0)).mean())
        print(f"  {label:10s} 실제 t={t0:+.2f}  귀무 t 표준편차 {null_t.std():.2f}  "
              f"p={p:.3f}  {'생존' if p < 0.05 else '기각'}")

    print(f"\n전·후반 (기준 {SPLIT}) — 롱숏")
    for label, _ in GROUPS:
        _, _, ls = legs(sigs[label])
        used_d = np.array([t for t, _ in days])[:len(ls)]
        first = dates[used_d] <= SPLIT
        ls = np.array(ls)
        out = []
        for lab, sel in (("전반", first), ("후반", ~first)):
            mu, tt = nw_tstat(ls[sel], FH)
            out.append(f"{lab} {mu*100:+.2f}% t={tt:+.2f}")
        print(f"  {label:10s}" + "   ".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
