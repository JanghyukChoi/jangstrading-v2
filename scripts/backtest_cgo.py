"""
"평균단가가 현재가보다 위/아래일 때 사는 게 나은가" 를 10년 데이터로 검정한다.

가설은 우리가 만든 게 아니라 Grinblatt & Han (2005) JFE 의 것이다. 미리 정해진
가설을 그대로 검정하는 게 과최적화를 막는 유일한 방법이다 — 파라미터를 찾아
헤매면 10년 데이터에서는 무엇이든 나온다.

  CGO_t = (P_t - R_{t-1}) / P_t          미실현 손익률
  R_t   = s_t P_t + (1 - s_t) R_{t-1}    회전율 가중 기준가격(= 평균단가)
  s_t   = 거래대금 / 시가총액             회전율

  CGO > 0  현재가가 평균단가보다 위 (보유자 이익 중)
  CGO < 0  현재가가 평균단가보다 아래 (보유자 손실 중)

논문의 예측: 처분효과 때문에 이익 난 사람은 너무 일찍 팔고 손실 난 사람은
버틴다. 그래서 CGO 가 높은 종목은 매도압력에 눌려 저평가되고 이후 초과수익이
난다. 즉 **주가가 평균단가보다 위일 때 사는 쪽**이 낫다는 예측이다.
개인투자자 직관("평균단가 밑이니 싸다")과 정반대다.

편향 통제
  분할보정  backtest_panel.py 참고. 안 하면 삼성전자가 분할일에 -98%.
  생존편향  상장폐지 464종목을 그대로 포함한다. 폐지 시점 마지막 가격으로
            청산 — 정리매매 폭락이 이미 반영된 가격이라 그나마 보수적이지만,
            완전히 0 이 되는 경우는 과소반영이다.
  선견편향  CGO 는 t 시점까지의 정보만 쓰고, 매수는 t+1 종가다.
  모멘텀    CGO 는 과거 수익률과 기계적으로 상관이 높다. 이중정렬과
            Fama-MacBeth 로 분리하지 않으면 모멘텀을 재발견하는 것에 불과하다.
  미시구조  동전주 제외(호가 단위 때문에 등락률이 튄다), 우선주 제외,
            동일가중과 시총가중을 둘 다 보고한다.
  다중검정  보유기간 1/3/6/12개월을 전부 보고한다. 좋은 것만 고르지 않는다.

실행: python scripts/backtest_cgo.py --panel <panel.npz>
"""

import argparse
import sys

import numpy as np

# 사전 확정 파라미터 (탐색하지 않는다)
MIN_PRICE = 1000        # 동전주 제외. 호가단위가 커서 등락률이 튄다
MIN_DAYS = 250          # 기준가격 형성에 최소 1년
MAX_INIT_W = 0.20       # 기준가격의 20% 이상이 초기값이면 제외
N_GROUPS = 5            # 5분위. 논문과 동일
MOM_SKIP, MOM_LEN = 21, 252   # 12-1 모멘텀 (최근 1개월 제외, 표준)
HOLDS = (1, 3, 6, 12)   # 보유기간(개월). 전부 보고한다
COST = 0.0038           # 왕복 거래비용: 증권거래세 + 수수료 + 슬리피지


def nw_tstat(x, lag):
    """Newey-West t 통계량. 보유기간이 겹치면 자기상관 때문에 단순 t 가 부풀려진다."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 3:
        return np.nan
    m = x.mean()
    e = x - m
    var = (e @ e) / n
    for L in range(1, min(lag, n - 1) + 1):
        c = (e[L:] @ e[:-L]) / n
        var += 2 * (1 - L / (lag + 1)) * c
    if var <= 0:
        return np.nan
    return m / np.sqrt(var / n)


def compute_cgo(price, turn):
    """회전율 가중 기준가격과 CGO. 논문의 재귀식 그대로."""
    T, N = price.shape
    R = np.full(N, np.nan)
    initw = np.ones(N)
    started = np.zeros(N, bool)
    nd = np.zeros(N, np.int32)

    cgo = np.full((T, N), np.nan, np.float32)
    iw = np.full((T, N), np.nan, np.float32)
    ndays = np.zeros((T, N), np.int16)

    for t in range(T):
        p = price[t].astype(np.float64)
        live = np.isfinite(p) & (p > 0)

        # 어제까지의 기준가격으로 오늘의 CGO. 오늘 거래는 아직 안 쓴다.
        use = live & started
        cgo[t, use] = ((p[use] - R[use]) / p[use]).astype(np.float32)
        iw[t] = initw
        ndays[t] = np.minimum(nd, 32767)

        new = live & ~started
        R[new] = p[new]
        started[new] = True
        initw[new] = 1.0

        upd = live & started & ~new
        s = turn[t].astype(np.float64)
        s = np.where(np.isfinite(s), np.clip(s, 0, 1), 0.0)
        R[upd] = s[upd] * p[upd] + (1 - s[upd]) * R[upd]
        initw[upd] *= (1 - s[upd])
        nd[live] += 1

    return cgo, iw, ndays


def month_ends(dates):
    """각 달의 마지막 거래일 인덱스."""
    ym = np.array([d[:7] for d in dates])
    return np.array([np.where(ym == m)[0][-1] for m in sorted(set(ym))])


def fwd_return(price, ok, i0, i1):
    """i0+1 종가 매수 -> i1+1 종가 매도. 상장폐지는 마지막 가격으로 청산."""
    T, N = price.shape
    e = min(i0 + 1, T - 1)
    x = min(i1 + 1, T - 1)
    entry = price[e].astype(np.float64)
    seg = price[e:x + 1]
    okseg = ok[e + 1:x + 1]

    last = np.full(N, np.nan)
    fin_all = np.isfinite(seg)
    has = fin_all.any(axis=0)
    idx_last = np.where(has, fin_all.shape[0] - 1 - np.argmax(fin_all[::-1], axis=0), -1)
    for j in np.where(has & np.isfinite(entry) & (entry > 0))[0]:
        k = idx_last[j]
        # 보유기간 중 설명 안 되는 가격 점프가 있으면 그 종목은 버린다
        if okseg.shape[0] and k > 0 and not okseg[:k, j].all():
            continue
        last[j] = seg[k, j]
    with np.errstate(invalid="ignore", divide="ignore"):
        return last / entry - 1


def qgroups(x, n):
    """분위 번호 0..n-1. 순위 기준 균등 분할."""
    g = np.full(len(x), -1, np.int8)
    v = np.where(np.isfinite(x))[0]
    if len(v) < n * 10:
        return g
    order = v[np.argsort(x[v], kind="stable")]
    edges = np.linspace(0, len(order), n + 1).astype(int)
    for k in range(n):
        g[order[edges[k]:edges[k + 1]]] = k
    return g


def wmean(r, w):
    m = np.isfinite(r) & np.isfinite(w) & (w > 0)
    if not m.any():
        return np.nan
    return float(np.sum(r[m] * w[m]) / np.sum(w[m]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", required=True)
    args = ap.parse_args()

    z = np.load(args.panel, allow_pickle=True)
    dates, tickers = z["dates"], z["tickers"]
    price, mcap, turn, ok = z["price"], z["mcap"], z["turn"], z["ok"]
    T, N = price.shape
    print("=" * 74)
    print(f"CGO 백테스트   {dates[0]} ~ {dates[-1]}   {T}일 x {N}종목")
    print("=" * 74)

    # 우선주 제외: 국내 종목코드는 보통주가 끝자리 0
    common = np.array([t[-1] == "0" for t in tickers])
    print(f"우선주·기타 제외 {int((~common).sum())}종목 -> 보통주 {int(common.sum())}종목")

    print("\n[1] 기준가격 · CGO 계산")
    cgo, iw, ndays = compute_cgo(price, turn)
    print(f"  CGO 관측 {int(np.isfinite(cgo).sum()):,}건")

    me = month_ends(dates)
    me = me[(me >= MIN_DAYS) & (me < T - 25)]
    print(f"  월말 리밸런싱 {len(me)}회 ({dates[me[0]]} ~ {dates[me[-1]]})")

    print("\n[2] 포트폴리오 구성")
    res = {h: {"ew": [], "vw": [], "dates": [], "turnover": []} for h in HOLDS}
    dbl = {k: [] for k in range(N_GROUPS)}
    fm_rows = []
    prev_hold = {h: None for h in HOLDS}
    nelig = []

    for i0 in me:
        c = cgo[i0].astype(np.float64)
        p0 = price[i0].astype(np.float64)
        mc = mcap[i0].astype(np.float64)
        elig = (common & np.isfinite(c) & np.isfinite(p0) & (p0 >= MIN_PRICE)
                & np.isfinite(mc) & (mc > 0)
                & (ndays[i0] >= MIN_DAYS) & (iw[i0] <= MAX_INIT_W))
        if elig.sum() < 200:
            continue
        nelig.append(int(elig.sum()))
        cc = np.where(elig, c, np.nan)
        g = qgroups(cc, N_GROUPS)

        ia, ib = i0 - MOM_SKIP, i0 - MOM_LEN
        mom = np.full(N, np.nan)
        if ib >= 0:
            with np.errstate(invalid="ignore", divide="ignore"):
                mom = price[ia].astype(np.float64) / price[ib].astype(np.float64) - 1
        rev = np.full(N, np.nan)
        if i0 - 21 >= 0:
            with np.errstate(invalid="ignore", divide="ignore"):
                rev = p0 / price[i0 - 21].astype(np.float64) - 1

        for h in HOLDS:
            i1 = i0 + h * 21
            if i1 >= T - 1:
                continue
            r = fwd_return(price, ok, i0, i1)
            row_ew, row_vw = [], []
            for k in range(N_GROUPS):
                sel = g == k
                with np.errstate(invalid="ignore"):
                    row_ew.append(float(np.nanmean(r[sel])) if sel.any() else np.nan)
                row_vw.append(wmean(r[sel], mc[sel]))
            res[h]["ew"].append(row_ew)
            res[h]["vw"].append(row_vw)
            res[h]["dates"].append(dates[i0])
            cur = set(np.where(g == N_GROUPS - 1)[0])
            pv = prev_hold[h]
            res[h]["turnover"].append(
                1.0 if pv is None or not cur else 1 - len(cur & pv) / len(cur))
            prev_hold[h] = cur

        # 모멘텀 이중정렬 + Fama-MacBeth (1개월 보유 기준)
        i1 = i0 + 21
        if i1 < T - 1:
            r1 = fwd_return(price, ok, i0, i1)
            mg = qgroups(np.where(elig, mom, np.nan), N_GROUPS)
            for k in range(N_GROUPS):
                sub = mg == k
                if sub.sum() < N_GROUPS * 10:
                    continue
                cg = qgroups(np.where(sub, cc, np.nan), N_GROUPS)
                with np.errstate(invalid="ignore"):
                    hi = float(np.nanmean(r1[cg == N_GROUPS - 1]))
                    lo = float(np.nanmean(r1[cg == 0]))
                if np.isfinite(hi) and np.isfinite(lo):
                    dbl[k].append(hi - lo)

            m = elig & np.isfinite(r1) & np.isfinite(mom) & np.isfinite(rev)
            if m.sum() > 200:
                fm_rows.append((r1[m], c[m], mom[m], np.log(mc[m]), rev[m],
                                np.nan_to_num(turn[i0][m].astype(float))))

    print(f"  회당 편입가능 종목 평균 {int(np.mean(nelig))}개")

    print("\n[3] CGO 5분위별 향후 수익률")
    print("    Q1 = 주가가 평균단가보다 한참 아래(보유자 손실 중)")
    print("    Q5 = 주가가 평균단가보다 한참 위(보유자 이익 중)\n")
    for h in HOLDS:
        ew = np.array(res[h]["ew"], float)
        vw = np.array(res[h]["vw"], float)
        if len(ew) == 0:
            continue
        sp_ew = ew[:, -1] - ew[:, 0]
        sp_vw = vw[:, -1] - vw[:, 0]
        lag = max(1, h - 1)
        tn = float(np.nanmean(res[h]["turnover"]))
        net = np.nanmean(sp_ew) - COST * tn * 2
        print(f"  보유 {h:>2}개월  (관측 {len(ew)}회)")
        print("    동일가중 " + "  ".join(f"Q{k+1} {np.nanmean(ew[:, k])*100:+6.2f}%"
                                          for k in range(N_GROUPS)))
        print("    시총가중 " + "  ".join(f"Q{k+1} {np.nanmean(vw[:, k])*100:+6.2f}%"
                                          for k in range(N_GROUPS)))
        print(f"    Q5-Q1  동일가중 {np.nanmean(sp_ew)*100:+.2f}% (t={nw_tstat(sp_ew, lag):+.2f})"
              f"   시총가중 {np.nanmean(sp_vw)*100:+.2f}% (t={nw_tstat(sp_vw, lag):+.2f})")
        print(f"    비용차감(동일가중) {net*100:+.2f}%   롱레그 회전율 {tn*100:.0f}%\n")

    print("[4] 모멘텀과 분리 — 모멘텀 5분위 안에서 다시 CGO 5분위, 1개월 보유")
    vals = []
    for k in range(N_GROUPS):
        if not dbl[k]:
            continue
        a = np.array(dbl[k], float)
        vals.append(np.nanmean(a))
        print(f"    모멘텀 Q{k+1}  CGO Q5-Q1 = {np.nanmean(a)*100:+.2f}%  "
              f"(t={nw_tstat(a, 1):+.2f})")
    if vals:
        print(f"    모멘텀 통제 후 평균 {np.mean(vals)*100:+.2f}%")

    print("\n[5] Fama-MacBeth — 1개월 수익률의 월별 단면회귀 (변수는 표준화)")
    if fm_rows:
        names = ["CGO", "모멘텀12-1", "log시총", "단기반전1M", "회전율"]
        coefs = []
        for r1, c1, m1, s1, v1, t1 in fm_rows:
            X = np.column_stack([c1, m1, s1, v1, t1])
            for j in range(X.shape[1]):
                lo, hi = np.nanpercentile(X[:, j], [1, 99])
                X[:, j] = np.clip(X[:, j], lo, hi)
                sd = X[:, j].std()
                X[:, j] = (X[:, j] - X[:, j].mean()) / (sd if sd > 0 else 1)
            ylo, yhi = np.nanpercentile(r1, [1, 99])
            y = np.clip(r1, ylo, yhi)
            A = np.column_stack([np.ones(len(y)), X])
            try:
                coefs.append(np.linalg.lstsq(A, y, rcond=None)[0])
            except np.linalg.LinAlgError:
                pass
        C = np.array(coefs)
        print(f"    단면 {len(C)}개월")
        for j, nm in enumerate(names):
            b = C[:, j + 1]
            print(f"    {nm:<10} {np.nanmean(b)*100:+.3f}%p / 1표준편차   "
                  f"t={nw_tstat(b, 1):+.2f}")

    print("\n[6] 기간 안정성 — 전반기/후반기 (1개월 보유, 동일가중 Q5-Q1)")
    ew = np.array(res[1]["ew"], float)
    ds = res[1]["dates"]
    if len(ew):
        sp = ew[:, -1] - ew[:, 0]
        half = len(sp) // 2
        for lab, a, b in (("전반기", 0, half), ("후반기", half, len(sp))):
            print(f"    {lab} {ds[a]}~{ds[b-1]}  {np.nanmean(sp[a:b])*100:+.2f}%  "
                  f"(t={nw_tstat(sp[a:b], 1):+.2f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
