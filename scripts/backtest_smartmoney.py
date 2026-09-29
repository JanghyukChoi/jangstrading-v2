"""
스마트머니 수급에 예측력이 있는가 — 정면 검정.

**질문이 하나가 아니다.** 섞으면 답이 안 나온다. 셋으로 나눈다.

  Q1 외국인·기관은 실제로 돈을 버는가?
      그들이 산 종목이 이후에 오르는가. 이건 "그들이 똑똑한가"의 질문이다.

  Q2 그 정보로 우리가 돈을 벌 수 있는가?
      Q1 이 참이어도 Q2 는 거짓일 수 있다. 수급은 **장 마감 후** 공개된다.
      우리가 살 수 있는 가장 빠른 시점은 다음날 종가다. 그 하루 사이에
      정보가 이미 가격에 들어갔다면 Q1 은 참, Q2 는 거짓이다.

  Q3 그 상관은 예측인가 가격충격인가?
      사면 오른다. 그래서 '수급과 수익률이 같이 움직인다'는 관찰은
      예측력의 증거가 아니다. 과거방향·동시점·미래방향을 다 재서 비교한다.

설계 원칙
  - 초과수익으로만 본다. 그날 같은 유니버스의 동일가중 평균을 뺀다.
    안 빼면 상승장에서 아무 신호나 양수가 나온다.
  - 중첩 수익률은 Newey-West 로 보정한다. h일 보유를 매일 시작하면
    관측이 h배 부풀려진다(원장 §16 "Sharpe 2.2인데 t 1.8").
  - 격자 전체를 보고한다. 좋은 칸만 고르지 않는다. 진짜 신호면
    이웃 칸도 같이 좋아야 한다(원장 §17 "고원").

실행
  python scripts/backtest_smartmoney.py --panel <panel.npz>
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
WINDOWS = (1, 5, 20, 60, 120)      # 수급 누적일
HORIZONS = (1, 5, 20, 60)          # 보유일
MIN_MCAP = 5e11                    # 시총 5,000억 이상. 초소형주 노이즈 제거
SPLIT = "2021-06-30"               # 전·후반 분리 기준. 숫자 보기 전에 고정


def nw_tstat(x, lag):
    """평균의 Newey-West t. x 는 일별 시계열."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 30:
        return np.nan, np.nan
    mu = x.mean()
    e = x - mu
    s = float(e @ e) / n
    for L in range(1, min(int(lag), n - 1) + 1):
        w = 1.0 - L / (lag + 1.0)
        s += 2.0 * w * float(e[L:] @ e[:-L]) / n
    if s <= 0:
        return mu, np.nan
    return mu, mu / np.sqrt(s / n)


def load_flows(dates, tickers):
    """스냅샷에서 주체별 일별 순매수(백만원) 패널을 만든다."""
    tidx = {t: i for i, t in enumerate(tickers)}
    out = {key: np.zeros((len(dates), len(tickers)), dtype=np.float32)
           for _, key in GROUPS}
    seen = 0
    for i, d in enumerate(dates):
        p = SNAPS / f"{d}.json"
        if not p.exists():
            continue
        try:
            snap = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        seen += 1
        for _, key in GROUPS:
            for tk, v in (snap.get(key) or {}).items():
                j = tidx.get(tk)
                if j is not None and isinstance(v, (int, float)):
                    out[key][i, j] = v
    return out, seen


def excess_returns(price, ok, mcap):
    """t -> t+1 의 1일 초과수익. 유니버스 동일가중 평균을 뺀다."""
    T, N = price.shape
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.full((T, N), np.nan)
        r[1:] = price[1:] / price[:-1] - 1.0
    r[~ok] = np.nan
    r[np.abs(r) > 0.45] = np.nan          # ±30% 제한 밖은 데이터 오류

    univ = (mcap >= MIN_MCAP) & np.isfinite(price) & (price > 0)
    # 그날의 유니버스 평균(다음날 수익률 기준)
    m = np.where(univ[:-1], r[1:], np.nan)
    mkt = np.nanmean(m, axis=1)
    exc = np.full((T, N), np.nan)
    exc[1:] = r[1:] - mkt[:, None]
    return exc, univ


def fwd(exc, h):
    """t 기준, t+1 부터 h일간 누적 초과수익(단순합). NaN 이 하나라도 있으면 NaN."""
    T, N = exc.shape
    out = np.full((T, N), np.nan)
    if h >= T - 1:
        return out
    # exc[i] 는 i-1 -> i 수익. t 다음날부터 h일 = exc[t+1 .. t+h]
    c = np.nancumsum(np.nan_to_num(exc, nan=0.0), axis=0)
    valid = np.isfinite(exc).astype(np.int32)
    cv = np.cumsum(valid, axis=0)
    for t in range(0, T - h - 1):
        out[t] = c[t + h] - c[t]
        bad = (cv[t + h] - cv[t]) < h
        out[t][bad] = np.nan
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", required=True)
    args = ap.parse_args()

    z = np.load(args.panel, allow_pickle=True)
    dates = [str(d) for d in z["dates"]]
    tickers = [str(t) for t in z["tickers"]]
    price = z["price"].astype(np.float64)
    mcap = z["mcap"].astype(np.float64)
    ok = z["ok"]
    T, N = price.shape
    print(f"패널 {T}일 x {N}종목  ({dates[0]} ~ {dates[-1]})")

    flows, seen = load_flows(dates, tickers)
    print(f"수급 스냅샷 {seen}일 적재")

    exc, univ = excess_returns(price, ok, mcap)
    print(f"유니버스: 시총 {MIN_MCAP/1e8:,.0f}억 이상 "
          f"= 일평균 {univ.sum(axis=1).mean():.0f}종목\n")

    dates_arr = np.array(dates)
    first = dates_arr <= SPLIT

    # ── Q3 먼저. 방향별 상관을 봐야 나머지 해석이 된다 ────────────────
    print("=" * 78)
    print("Q3. 수급-수익률 관계는 언제 나타나는가 (자금가중 초과수익, %)")
    print("    과거=매수 직전 20일 / 동시점=매수 당일 / 미래=발표 다음날부터 20일")
    print("=" * 78)
    print(f"{'주체':8s}{'과거 20일':>12s}{'동시점 1일':>12s}"
          f"{'미래 20일':>12s}{'t(미래)':>10s}")

    # 호라이즌별 누적 초과수익은 여기서 한 번만 만든다. 루프 안에서 다시
    # 계산하면 2,520일 x 3,234종목을 수십 번 훑게 된다.
    FWD = {h: fwd(exc, h) for h in HORIZONS}
    print("  누적 초과수익 사전계산 완료: " + ", ".join(f"{h}일" for h in HORIZONS))

    back20 = np.full((T, N), np.nan)
    back20[20:] = FWD[20][:-20]               # t-20 -> t 누적
    same = exc                                 # t-1 -> t
    f20 = FWD[20]

    for label, key in GROUPS:
        w = flows[key]
        row = []
        for mat in (back20, same, f20):
            num = np.where(univ & np.isfinite(mat), w * np.nan_to_num(mat), 0.0).sum(axis=1)
            den = np.where(univ & np.isfinite(mat), np.abs(w), 0.0).sum(axis=1)
            series = np.where(den > 0, num / np.where(den > 0, den, 1), np.nan)
            row.append(series)
        mu_b, _ = nw_tstat(row[0], 20)
        mu_s, _ = nw_tstat(row[1], 5)
        mu_f, t_f = nw_tstat(row[2], 20)
        print(f"{label:8s}{mu_b*100:>11.3f}%{mu_s*100:>11.3f}%"
              f"{mu_f*100:>11.3f}%{t_f:>10.2f}")

    # ── Q1/Q2. 횡단면 10분위 격자 ────────────────────────────────────
    for label, key in GROUPS:
        w = flows[key]
        print("\n" + "=" * 78)
        print(f"Q1/Q2. {label} 누적순매수/시가총액 — 상위10% - 하위10% 초과수익(%)")
        print("       진입: 발표 다음날 종가 (당일 종가 매수는 불가능하다)")
        print("=" * 78)
        header = "누적\\보유" + "".join(f"{h:>8d}일" for h in HORIZONS)
        print(header + f"{'단조성':>10s}")

        cum = np.cumsum(np.nan_to_num(w, nan=0.0), axis=0)
        for W in WINDOWS:
            sig = np.full((T, N), np.nan)
            if W < T:
                sig[W:] = (cum[W:] - cum[:-W]) * 1e6 / np.where(mcap[W:] > 0, mcap[W:], np.nan)
            cells, rhos = [], []
            for h in HORIZONS:
                f = FWD[h]
                daily, dec_means = [], np.zeros((10,))
                dec_cnt = np.zeros((10,))
                for t in range(W, T - h - 1):
                    m = univ[t] & np.isfinite(sig[t]) & np.isfinite(f[t])
                    if m.sum() < 100:
                        continue
                    s, r = sig[t][m], f[t][m]
                    q = np.quantile(s, [0.1, 0.9])
                    lo, hi = s <= q[0], s >= q[1]
                    if lo.sum() < 5 or hi.sum() < 5:
                        continue
                    daily.append(r[hi].mean() - r[lo].mean())
                    # 단조성용 10분위 평균
                    edges = np.quantile(s, np.linspace(0, 1, 11))
                    idx = np.clip(np.searchsorted(edges, s, side="right") - 1, 0, 9)
                    for d in range(10):
                        sel = idx == d
                        if sel.any():
                            dec_means[d] += r[sel].mean()
                            dec_cnt[d] += 1
                mu, tt = nw_tstat(daily, max(h, 5))
                cells.append((mu, tt))
                with np.errstate(invalid="ignore"):
                    dm = dec_means / np.where(dec_cnt > 0, dec_cnt, np.nan)
                if np.isfinite(dm).all():
                    rhos.append(np.corrcoef(np.arange(10), dm)[0, 1])
            line = f"{W:>6d}일   "
            for mu, tt in cells:
                star = "*" if abs(tt) >= 2 else " "
                line += f"{mu*100:>+7.2f}{star}"
            rho = np.mean(rhos) if rhos else np.nan
            print(line + f"{rho:>10.2f}")
            line2 = "         t"
            for mu, tt in cells:
                line2 += f"{tt:>8.2f}"
            print(line2)

        print("  * = |t| >= 2.0 (Newey-West, 중첩보정).  단조성 = 10분위 평균과 순위의 상관")

    print("\n" + "=" * 78)
    print("전·후반 분리 (기준 " + SPLIT + ") — 20일 누적 / 20일 보유만")
    print("=" * 78)
    for label, key in GROUPS:
        w = flows[key]
        cum = np.cumsum(np.nan_to_num(w, nan=0.0), axis=0)
        W, h = 20, 20
        sig = np.full((T, N), np.nan)
        sig[W:] = (cum[W:] - cum[:-W]) * 1e6 / np.where(mcap[W:] > 0, mcap[W:], np.nan)
        f = FWD[h]
        out = []
        for lab, sel in (("전반", first), ("후반", ~first)):
            daily = []
            for t in range(W, T - h - 1):
                if not sel[t]:
                    continue
                m = univ[t] & np.isfinite(sig[t]) & np.isfinite(f[t])
                if m.sum() < 100:
                    continue
                s, r = sig[t][m], f[t][m]
                q = np.quantile(s, [0.1, 0.9])
                lo, hi = s <= q[0], s >= q[1]
                if lo.sum() < 5 or hi.sum() < 5:
                    continue
                daily.append(r[hi].mean() - r[lo].mean())
            mu, tt = nw_tstat(daily, h)
            out.append(f"{lab} {mu*100:+.2f}% t={tt:+.2f}")
        print(f"  {label:8s}" + "   ".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
