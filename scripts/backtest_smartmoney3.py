"""
연기금 역방향 신호를 반증한다 — 순열검정.

왜 필요한가
  문헌 조사에서 나온 경고: 어떤 공개 검증 프레임워크는 **신호가 없는 합성
  데이터가 46% 의 시도에서 5/6 폴드를 통과**했다. 원장 §17 도 "셔플 귀무
  없이 채택 금지"를 못박는다. t = -4.03 은 그 자체로는 증거가 아니다.

귀무가설의 설계가 핵심이다
  매일 종목 라벨을 따로 섞으면 안 된다. 실제 신호는 120일 누적이라 시계열로
  강하게 지속되는데, 매일 새로 섞으면 귀무 표본은 지속성이 없어져 분산이
  과소평가되고 검정이 **너무 관대**해진다.

  그래서 **종목 라벨 순열 하나를 뽑아 전 기간에 똑같이 적용**한다.
    - 신호의 시계열 지속성      보존
    - 종목별 수익률 구조·상관    보존
    - 신호와 그 종목 수익률의 연결  파괴  <- 이것만 끊는다

  이 귀무 아래에서 실제 t 가 어디에 있는지 본다.

같이 보는 것
  - 외국인·기관도 같이 돌린다. 이쪽은 실제값이 귀무 한가운데 있어야 정상이다
    (1차에서 t = -0.03, -0.77). 그렇지 않으면 검정 자체가 틀린 것이다.

실행
  python scripts/backtest_smartmoney3.py --panel <panel.npz> --draws 300
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
W, H = 120, 60


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", required=True)
    ap.add_argument("--draws", type=int, default=300)
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

    flows = load_flows(dates, tickers)
    rng = np.random.default_rng(20260929)

    # 날짜별 유효 마스크를 미리 굳혀 둔다. 순열마다 다시 만들면 느리다.
    days = []
    for t in range(W, T - H - 1):
        m = univ[t] & np.isfinite(f[t])
        if m.sum() >= 100:
            days.append((t, np.where(m)[0]))
    print(f"검정일 {len(days):,}일 · 순열 {args.draws}회 · 칸 = {W}일 누적/{H}일 보유\n")

    def longshort(sig, perm=None):
        """상위10% - 하위10% 일별 시계열. perm 은 종목 라벨 치환(전 기간 동일)."""
        out = []
        for t, idx in days:
            s = sig[t][idx if perm is None else perm[idx]]
            rr = f[t][idx]
            good = np.isfinite(s)
            if good.sum() < 100:
                continue
            s2, r2 = s[good], rr[good]
            q = np.quantile(s2, [0.1, 0.9])
            hi, lo = s2 >= q[1], s2 <= q[0]
            if hi.sum() < 5 or lo.sum() < 5:
                continue
            out.append(r2[hi].mean() - r2[lo].mean())
        return out

    print("=" * 76)
    print("순열검정 — 종목 라벨을 섞어 신호-수익률 연결만 끊는다")
    print("  (신호의 시계열 지속성과 종목별 수익률 구조는 그대로 둔다)")
    print("=" * 76)
    print(f"{'주체':8s}{'실제 롱숏':>12s}{'실제 t':>9s}"
          f"{'귀무 t 평균':>12s}{'귀무 t 표준편차':>15s}{'양측 p':>10s}{'판정':>8s}")

    for label, key in GROUPS:
        cum = np.cumsum(np.nan_to_num(flows[key], nan=0.0), axis=0)
        sig = np.full((T, N), np.nan)
        sig[W:] = (cum[W:] - cum[:-W]) * 1e6 / np.where(mcap[W:] > 0, mcap[W:], np.nan)

        mu0, t0 = nw_tstat(longshort(sig), H)

        null_t = []
        for d in range(args.draws):
            perm = rng.permutation(N)
            _, tt = nw_tstat(longshort(sig, perm), H)
            if np.isfinite(tt):
                null_t.append(tt)
        null_t = np.array(null_t)
        # 양측 p — 귀무에서 |t| 가 실제만큼 극단적인 비율
        p = float((np.abs(null_t) >= abs(t0)).mean())
        verdict = "생존" if p < 0.05 else "기각"
        print(f"{label:8s}{mu0*100:>11.2f}%{t0:>9.2f}"
              f"{null_t.mean():>12.2f}{null_t.std():>15.2f}{p:>10.3f}{verdict:>8s}")

    print("\n  귀무 t 의 표준편차가 1 근처면 Newey-West 보정이 제대로 된 것이다.")
    print("  1 보다 크게 나오면 t 가 부풀려져 있다는 뜻이고, p 값이 진짜 판정이다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
