"""
개인 수급 온도계 — "오늘 개인 매수의 몇 %가 하락 중 매수였나" 가 시장을 예측하는가.

**판정 규칙을 숫자 보기 전에 확정한다.** 이 세션에서 v1->v2->v3 반복 튜닝이
다중검정이었다는 걸 확인했고, 사내 원장 §17.1 도 "검증표본을 본 뒤 변형을
고르면 안 된다"고 못박는다. 그래서 아래를 먼저 적어 둔다.

지표
    R_t = (그날 하락한 종목에 들어간 개인 순매수 금액) / (전체 개인 순매수 금액)
    개인이 순매수한 종목만 센다(순매도는 제외). 금액 가중이라 대형주가 지배한다.

    원장의 Q1~Q4 분해에서 Q2(어제↑ 오늘↓) + Q4(어제↓ 오늘↓) 에 해당한다.
    평시 약 74% 로 보고돼 있다.

**반드시 통제해야 하는 것 — 이게 이 검정의 핵심이다.**
    시장이 빠진 날은 하락 종목이 많으니 R_t 가 기계적으로 올라간다. 통제 없이
    R_t 로 수익률을 예측하면 그건 **그날의 시장 수익률을 다시 쓰는 것**이고,
    단기 반전을 재발견하는 것에 불과하다. 그래서 그날 지수 수익률(ret_t)과
    최근 5일 수익률을 통제변수로 넣고 **R_t 의 증분 설명력**만 본다.

    원장 §16 의 "가격이 이미 말해주는 것을 통제한 뒤에도 수급이 추가 정보를
    갖는가" 와 같은 질문이다.

사전 등록 판정 규칙
    1. 통제 후 t 는 **날짜 수가 아니라 독립 관측 수**로 판단한다. Newey-West 를
       쓰되 lag 을 두 가지로 본다.
         lag = h        중첩 수익률만 보정
         lag = max(h,21) 지표 자체의 지속성까지 보정. **이쪽을 판정에 쓴다.**
       설명변수가 강하게 자기상관하는 예측회귀에서는 h 만으로는 SE 가
       과소추정된다(원장 §2-3 의 "느린 팩터의 NW lag 과소보정"과 같은 문제).
    2. **전반기·후반기 모두** 같은 부호에 |t| > 1.5 여야 한다.
    3. 전체 표본 통제 후 |t| >= 2.0 이어야 한다.
    4. 1~3 을 모두 만족하지 못하면 **예측 지표로 쓰지 않는다.** 화면에는
       "오늘 시장 상태" 관측치로만 쓰거나, 아예 만들지 않는다.

    호라이즌 1/5/20일을 전부 보고한다. 좋은 것만 고르지 않는다.

한계(미리 적어 둔다)
    시장 수준 지표는 독립 관측이 적다. 13년 = 2,600영업일이지만 20일 호라이즌
    기준 독립 관측은 130개뿐이다. 원장 §1 도 "극단적 외국인 매도는 13년에
    2~3번뿐이라 백테스트로 답할 수 있는 질문이 아니다"라고 적는다.
    여기서 유의하지 않게 나와도 "효과 없음"이 아니라 "이 표본으로는 모른다"에
    가까울 수 있다. 그 구분을 결론에 적는다.

실행
  python scripts/backtest_retail_gauge.py --panel <panel.npz>
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent.parent
FLOWS = BASE / "scripts" / "backtest_data" / "flows"
KOSPI = BASE / "public" / "data" / "kospi-history.json"

HORIZONS = (1, 5, 20)
SPLIT = "2021-06-30"     # 표본 절반. 날짜로 미리 고정한다.


def nw_t(y, X, lag):
    """OLS 후 마지막 계수의 Newey-West t. X 는 상수항 포함."""
    n = len(y)
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    lag = max(1, int(lag))
    e = y - X @ b
    XtX_inv = np.linalg.pinv(X.T @ X)
    S = (X * e[:, None]).T @ (X * e[:, None])
    for L in range(1, min(lag, n - 1) + 1):
        w = 1 - L / (lag + 1)
        A = (X[L:] * e[L:, None]).T @ (X[:-L] * e[:-L, None])
        S += w * (A + A.T)
    V = XtX_inv @ S @ XtX_inv
    se = np.sqrt(np.diag(V))
    return b, b / np.where(se > 0, se, np.nan)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", required=True)
    args = ap.parse_args()

    z = np.load(args.panel, allow_pickle=True)
    dates, tickers = z["dates"], z["tickers"]
    price, ok = z["price"], z["ok"]
    tidx = {t: i for i, t in enumerate(tickers)}

    files = sorted(p for p in FLOWS.glob("*.json") if p.stem != "_progress")
    print(f"개인 수급 파일 {len(files)}종목")

    # 일별 (하락종목 개인매수 금액, 전체 개인매수 금액)
    dn = np.zeros(len(dates))
    tot = np.zeros(len(dates))
    didx = {d.replace("-", ""): i for i, d in enumerate(dates)}

    used = 0
    for f in files:
        j = tidx.get(f.stem)
        if j is None:
            continue
        used += 1
        flows = json.loads(f.read_text(encoding="utf-8"))
        for ymd, (indi, _corp) in flows.items():
            if indi <= 0:                       # 개인 순매수인 날만
                continue
            i = didx.get(ymd)
            if i is None or i == 0 or not ok[i, j]:
                continue
            p0, p1 = price[i - 1, j], price[i, j]
            if not np.isfinite(p0) or not np.isfinite(p1) or p0 <= 0:
                continue
            tot[i] += indi
            if p1 < p0:
                dn[i] += indi
    print(f"  패널과 매칭된 종목 {used}개")

    valid = tot > 0
    gauge = np.where(valid, dn / np.where(tot > 0, tot, 1), np.nan)
    print(f"  지표 산출일 {int(valid.sum()):,}일 "
          f"({dates[valid][0]} ~ {dates[valid][-1]})")
    g = gauge[valid]
    print(f"  분포: 평균 {np.nanmean(g)*100:.1f}%  중앙 {np.nanmedian(g)*100:.1f}%  "
          f"10%tile {np.nanpercentile(g,10)*100:.1f}%  90%tile {np.nanpercentile(g,90)*100:.1f}%")

    # KOSPI 수익률
    kh = json.loads(KOSPI.read_text(encoding="utf-8"))
    kv = np.array([kh.get(d, np.nan) for d in dates], dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        kret = np.concatenate([[np.nan], kv[1:] / kv[:-1] - 1])

    print("\n지표가 KOSPI 를 예측하는가 — 통제 전/후")
    print("  통제변수: 그날 지수 수익률, 최근 5일 지수 수익률")
    print(f"{'H':>4}{'관측일':>8}{'독립':>6}{'통제전 t':>10}{'통제후 계수':>13}"
          f"{'t(lag=h)':>10}{'t(lag>=21)':>12}")
    results = {}
    for h in HORIZONS:
        fwd = np.full(len(dates), np.nan)
        if h < len(dates):
            with np.errstate(invalid="ignore", divide="ignore"):
                fwd[:-h] = kv[h:] / kv[:-h] - 1
        r5 = np.full(len(dates), np.nan)
        with np.errstate(invalid="ignore", divide="ignore"):
            r5[5:] = kv[5:] / kv[:-5] - 1

        m = valid & np.isfinite(fwd) & np.isfinite(gauge) & np.isfinite(kret) & np.isfinite(r5)
        y = fwd[m]
        gz = (gauge[m] - gauge[m].mean()) / gauge[m].std()

        X0 = np.column_stack([np.ones(len(y)), gz])
        _, t0 = nw_t(y, X0, h)
        X1 = np.column_stack([np.ones(len(y)), kret[m], r5[m], gz])
        b1, t1 = nw_t(y, X1, h)
        _, t2 = nw_t(y, X1, max(h, 21))     # 지표 지속성까지 보정 — 판정용
        results[h] = (b1[-1], t2[-1])
        print(f"{h:>4}{int(m.sum()):>8,}{int(m.sum()//h):>6,}"
              f"{t0[-1]:>10.2f}{b1[-1]*100:>+12.3f}%{t1[-1]:>10.2f}{t2[-1]:>12.2f}")

    print(f"\n전반/후반 분리 (기준 {SPLIT}) — 통제 후")
    for h in HORIZONS:
        fwd = np.full(len(dates), np.nan)
        if h < len(dates):
            with np.errstate(invalid="ignore", divide="ignore"):
                fwd[:-h] = kv[h:] / kv[:-h] - 1
        r5 = np.full(len(dates), np.nan)
        with np.errstate(invalid="ignore", divide="ignore"):
            r5[5:] = kv[5:] / kv[:-5] - 1
        line = f"  {h:>2}일  "
        for lab, sel in (("전반", dates <= SPLIT), ("후반", dates > SPLIT)):
            m = (valid & sel & np.isfinite(fwd) & np.isfinite(gauge)
                 & np.isfinite(kret) & np.isfinite(r5))
            if m.sum() < 200:
                line += f"{lab} 표본부족   "
                continue
            y = fwd[m]
            gz = (gauge[m] - gauge[m].mean()) / gauge[m].std()
            X = np.column_stack([np.ones(len(y)), kret[m], r5[m], gz])
            b, t = nw_t(y, X, max(h, 21))
            line += f"{lab} {b[-1]*100:+.3f}% t={t[-1]:+.2f} ({int(m.sum()//h)}독립)   "
        print(line)

    print("\n판정 (사전 등록 규칙)")
    ok_all = all(abs(results[h][1]) >= 2.0 for h in HORIZONS)
    print(f"  규칙3 전체 통제후 |t|>=2.0 (lag>=21) : {'통과' if ok_all else '미통과'}"
          f"  (t = {', '.join(f'{results[h][1]:+.2f}' for h in HORIZONS)})")
    print("  -> 미통과면 예측 지표로 쓰지 않는다. 관측치로만 쓰거나 만들지 않는다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
