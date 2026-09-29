"""
1차 검정에서 나온 것들을 반증한다.

1차 결과
  - 외국인·기관: 미래 예측력 사실상 0. 과거·동시점에만 관계가 있다.
  - 연기금: 격자 전체가 음수, 단조성 -0.72, 양 구간 같은 부호.

**연기금 결과를 그대로 믿으면 안 된다.** 연기금은 대형주를 산다. 이 기간
대형주가 소형주에 졌다면 "연기금이 산 종목이 진다"는 그냥 **사이즈 효과**다.
그러면 수급 정보가 아니라 시가총액을 다시 발견한 것에 불과하다.

그래서 여기서 셋을 한다.
  A. 다리 분해   상위10%가 지는 것인가, 하위10%가 이기는 것인가.
                 공매도가 제한된 시장에서 쓸 수 있는 건 회피 프레이밍뿐이라
                 상위10%가 유니버스보다 지는지가 실질적 질문이다.
  B. 사이즈 중립 매일 log(시총) 3분위 안에서만 순위를 매긴다. 사이즈가
                 설명하는 부분을 빼고도 남는지 본다.
  C. 모멘텀 중립 1차에서 "수급은 이미 오른 종목에 몰린다"(과거20일 +2.8%)가
                 확인됐다. 과거 20일 수익률 3분위 안에서도 같은 걸 한다.
                 수급이 모멘텀의 대리변수인지 가른다.

C 가 핵심이다. 사이즈와 모멘텀을 둘 다 통제하고도 살아남으면 그건 수급
고유의 정보다. 사라지면 "수급 신호"는 이름만 수급이다.

실행
  python scripts/backtest_smartmoney2.py --panel <panel.npz>
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
SNAPS = BASE / "scripts" / "backtest_data" / "snapshots"

GROUPS = [("외국인", "foreign_1d"), ("기관", "inst_1d"), ("연기금", "pension_1d")]
MIN_MCAP = 5e11
W, H = 120, 60          # 1차에서 가장 강했던 칸. 여기서만 반증한다.
SPLIT = "2021-06-30"
COST = 0.005            # 왕복 거래비용 0.5%


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
    tidx = {t: i for i, t in enumerate(tickers)}
    out = {k: np.zeros((len(dates), len(tickers)), dtype=np.float32) for _, k in GROUPS}
    for i, d in enumerate(dates):
        p = SNAPS / f"{d}.json"
        if not p.exists():
            continue
        try:
            snap = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for _, key in GROUPS:
            for tk, v in (snap.get(key) or {}).items():
                j = tidx.get(tk)
                if j is not None and isinstance(v, (int, float)):
                    out[key][i, j] = v
    return out


def build(price, ok, mcap):
    T, N = price.shape
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.full((T, N), np.nan)
        r[1:] = price[1:] / price[:-1] - 1.0
    r[~ok] = np.nan
    r[np.abs(r) > 0.45] = np.nan
    univ = (mcap >= MIN_MCAP) & np.isfinite(price) & (price > 0)
    mkt = np.nanmean(np.where(univ[:-1], r[1:], np.nan), axis=1)
    exc = np.full((T, N), np.nan)
    exc[1:] = r[1:] - mkt[:, None]
    return exc, univ


def fwd(exc, h):
    T, N = exc.shape
    out = np.full((T, N), np.nan)
    c = np.nancumsum(np.nan_to_num(exc, nan=0.0), axis=0)
    cv = np.cumsum(np.isfinite(exc).astype(np.int32), axis=0)
    for t in range(0, T - h - 1):
        out[t] = c[t + h] - c[t]
        out[t][(cv[t + h] - cv[t]) < h] = np.nan
    return out


def tercile(x, m):
    """유효한 값들을 3분위로 나눈 라벨(0,1,2). 무효는 -1."""
    lab = np.full(x.shape, -1, dtype=np.int8)
    v = x[m]
    if v.size < 30:
        return lab
    q = np.quantile(v, [1 / 3, 2 / 3])
    lab[m] = np.digitize(v, q)
    return lab


def run(sig, f, univ, T, control=None):
    """상위10%/하위10% 의 유니버스 대비 초과수익 시계열.

    control 이 주어지면 그 3분위 **안에서** 순위를 매긴 뒤 합친다.
    (사이즈·모멘텀이 설명하는 부분을 빼고 보기 위한 것)
    """
    hi_s, lo_s, ls_s = [], [], []
    for t in range(W, T - H - 1):
        m = univ[t] & np.isfinite(sig[t]) & np.isfinite(f[t])
        if m.sum() < 100:
            continue
        base = np.nanmean(f[t][m])
        hi_mask = np.zeros(m.shape, dtype=bool)
        lo_mask = np.zeros(m.shape, dtype=bool)
        groups = [m] if control is None else [
            m & (control[t] == g) for g in (0, 1, 2)]
        for gm in groups:
            if gm.sum() < 30:
                continue
            s = sig[t][gm]
            q = np.quantile(s, [0.1, 0.9])
            idx = np.where(gm)[0]
            hi_mask[idx[s >= q[1]]] = True
            lo_mask[idx[s <= q[0]]] = True
        if hi_mask.sum() < 5 or lo_mask.sum() < 5:
            continue
        hi = np.nanmean(f[t][hi_mask])
        lo = np.nanmean(f[t][lo_mask])
        hi_s.append(hi - base)
        lo_s.append(lo - base)
        ls_s.append(hi - lo)
    return hi_s, lo_s, ls_s


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

    exc, univ = build(price, z["ok"], mcap)
    flows = load_flows(dates, tickers)
    f = fwd(exc, H)
    mom = np.full((T, N), np.nan)          # 과거 20일 초과수익 (모멘텀 통제용)
    f20 = fwd(exc, 20)
    mom[20:] = f20[:-20]

    with np.errstate(invalid="ignore", divide="ignore"):
        logmc = np.where(mcap > 0, np.log(mcap), np.nan)

    print(f"패널 {T}일 x {N}종목 · 유니버스 시총 {MIN_MCAP/1e8:,.0f}억 이상")
    print(f"검정 칸: {W}일 누적 순매수 / 시가총액, {H}일 보유, 발표 다음날 진입")
    print(f"거래비용 왕복 {COST*100:.1f}% 가정\n")

    # 통제변수 3분위 라벨 (매일)
    size_lab = np.full((T, N), -1, dtype=np.int8)
    mom_lab = np.full((T, N), -1, dtype=np.int8)
    for t in range(W, T - H - 1):
        m = univ[t] & np.isfinite(logmc[t])
        size_lab[t] = tercile(logmc[t], m)
        m2 = univ[t] & np.isfinite(mom[t])
        mom_lab[t] = tercile(mom[t], m2)

    print("=" * 84)
    print("A. 다리 분해 — 유니버스 평균 대비 (공매도 제한 시장에선 상위10%가 실질 질문)")
    print("=" * 84)
    print(f"{'주체':8s}{'상위10%':>12s}{'t':>8s}{'하위10%':>12s}{'t':>8s}"
          f"{'롱숏':>10s}{'t':>8s}")
    results = {}
    for label, key in GROUPS:
        cum = np.cumsum(np.nan_to_num(flows[key], nan=0.0), axis=0)
        sig = np.full((T, N), np.nan)
        sig[W:] = (cum[W:] - cum[:-W]) * 1e6 / np.where(mcap[W:] > 0, mcap[W:], np.nan)
        results[label] = sig
        hi, lo, ls = run(sig, f, univ, T)
        mh, th = nw_tstat(hi, H)
        ml, tl = nw_tstat(lo, H)
        ms, ts = nw_tstat(ls, H)
        print(f"{label:8s}{mh*100:>11.2f}%{th:>8.2f}{ml*100:>11.2f}%{tl:>8.2f}"
              f"{ms*100:>9.2f}%{ts:>8.2f}")

    print("\n" + "=" * 84)
    print("B/C. 통제 — 같은 사이즈끼리, 같은 모멘텀끼리만 비교하면 남는가")
    print("=" * 84)
    print(f"{'주체':8s}{'통제없음':>14s}{'사이즈 중립':>16s}{'모멘텀 중립':>16s}")
    for label, _ in GROUPS:
        sig = results[label]
        cells = []
        for ctrl in (None, size_lab, mom_lab):
            _, _, ls = run(sig, f, univ, T, control=ctrl)
            mu, tt = nw_tstat(ls, H)
            cells.append(f"{mu*100:+.2f}% t={tt:+.2f}")
        print(f"{label:8s}{cells[0]:>14s}{cells[1]:>16s}{cells[2]:>16s}")

    print("\n" + "=" * 84)
    print("D. 연기금 상위10% 회피 전략 — 전·후반, 거래비용 반영")
    print("=" * 84)
    sig = results["연기금"]
    hi, _, _ = run(sig, f, univ, T)
    # run() 은 날짜를 안 돌려주므로 같은 규칙으로 날짜를 다시 만든다
    used = []
    for t in range(W, T - H - 1):
        m = univ[t] & np.isfinite(sig[t]) & np.isfinite(f[t])
        if m.sum() < 100:
            continue
        s = sig[t][m]
        q = np.quantile(s, [0.1, 0.9])
        if (s >= q[1]).sum() < 5 or (s <= q[0]).sum() < 5:
            continue
        used.append(t)
    used = np.array(used)
    hi = np.array(hi)
    assert len(used) == len(hi), f"{len(used)} != {len(hi)}"
    first = dates[used] <= SPLIT
    for lab, sel in (("전체", np.ones(len(hi), bool)), ("전반", first), ("후반", ~first)):
        mu, tt = nw_tstat(hi[sel], H)
        print(f"  {lab:6s} 상위10% 초과수익 {mu*100:+.2f}%  t={tt:+.2f}  "
              f"(관측 {sel.sum():,}일, 독립 ~{sel.sum()//H})")
    mu, _ = nw_tstat(hi, H)
    print(f"\n  회피 가치: 유니버스 대신 상위10%를 빼면 {H}일당 {-mu*100:+.2f}%p")
    print(f"  {COST*100:.1f}% 비용으로 롱숏을 하면 {mu*100 - COST*100:+.2f}% — "
          f"{'생존' if abs(mu) > COST else '비용에 먹힘'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
