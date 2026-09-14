"""
회전율 가중 기준가격 (turnover-weighted reference price)

Grinblatt & Han (2005), "Prospect theory, mental accounting, and momentum",
Journal of Financial Economics 78(2) 의 기준가격을 투자주체별로 확장한 것.

기존 add_avg_cost.py / kis_fetch.calc_avg_cost 의 이동평균 원가법은 세 가지가
틀려 있었다.

  1. 120 영업일 전 보유량을 0 으로 가정했다. 삼성전자 외국인은 실제로 상장주식의
     46.64%(27.3억주)를 들고 있는데, 6 개월 순매도가 누적되면 포지션이 음수가 되어
     "보유 없음"으로 값을 버렸다.
  2. 주체의 체결가를 몰라 시장 전체 VWAP(거래대금/거래량)으로 대용했다.
     실제로는 주체별 매수대금/매수량이 제공된다.
  3. 포지션이 0 이하가 되면 평균단가를 리셋했다. 근거 없는 규칙이다.

이 모듈의 방식:

    w_n = B_n · Π_{m>n} (1 − s_m)          (n 시점 매수분이 오늘까지 남아있을 가중치)
    R   = Σ w_n · P_n / Σ w_n              (기준가격)
    CGO = (P_T − R) / P_T                  (미실현 손익률)

  B_n = 그날 주체의 매수 수량
  P_n = 그날 주체의 실제 매수 체결단가 (매수대금 / 매수량)
  s_m = 그날의 이탈률(회전율)

s_m 을 무엇으로 두느냐가 주체마다 다르다. 보유량 공시가 외국인에만 있기 때문이다.

  외국인  s = 외국인 매도량 / 그날 외국인 보유량
          보유량은 현재 공시치(frgn_hldn_qty)에서 순매수를 역산해 복원한다. 정확하다.
  기관    s = 시장 거래량 / 상장주식수  (원 논문의 시장 회전율)
          기관 보유량 공시가 없어서, "기관이 산 주식도 시장 평균 속도로 손바뀜한다"고
          본다. 근사지만 원 논문이 전체 주주에 대해 쓰는 바로 그 가정이다.

시작 보유량을 가정할 필요가 없다는 점이 핵심이다. 곱셈항이 오래된 매수분을 자연히
감쇠시키므로, 관측 구간이 길수록 초기 조건의 영향이 사라진다. 원 논문은 5 년을 쓰고
3~7 년에 결과가 안정적이라고 보고한다.
"""

from collections import defaultdict


def _f(v):
    try:
        return float(str(v).strip() or 0)
    except (TypeError, ValueError):
        return 0.0


def _i(v):
    try:
        return int(float(str(v).strip() or 0))
    except (TypeError, ValueError):
        return 0


# 주체별 KIS 필드 접두사
GROUPS = {
    "foreign": "frgn",
    "institution": "orgn",
}


def _series(rows, prefix):
    """주체의 일별 (매수량, 매수단가, 매도량) 시계열."""
    out = []
    for r in rows:
        buy_vol = _i(r.get(f"{prefix}_shnu_vol"))
        # 대금은 백만원 단위
        buy_amt = _i(r.get(f"{prefix}_shnu_tr_pbmn")) * 1_000_000
        sell_vol = _i(r.get(f"{prefix}_seln_vol"))
        net = _i(r.get(f"{prefix}_ntby_qty")) or (buy_vol - sell_vol)
        price = (buy_amt / buy_vol) if buy_vol > 0 and buy_amt > 0 else 0.0
        out.append({"buy": buy_vol, "price": price, "sell": sell_vol, "net": net})
    return out


def _holdings_path(series, holdings_now):
    """현재 보유량에서 순매수를 역산해 일별 보유량을 복원한다.

    H_T = holdings_now, H_{t-1} = H_t − net_t
    """
    n = len(series)
    h = [0] * n
    h[-1] = holdings_now
    for i in range(n - 1, 0, -1):
        h[i - 1] = h[i] - series[i]["net"]
    return h


def reference_price(rows, group, holdings_now=None, shares_outstanding=None):
    """주체의 회전율 가중 기준가격.

    Returns dict 또는 None:
        reference   기준가격(원)
        cgo         미실현 손익률 (현재가 대비, %)
        coverage    가중치가 실린 매수 건수 / 전체 관측일
        basis       [(가격대, 비중%)] 매물대 분포 (가격 오름차순, 최대 12구간)
        method      "holdings" | "market_turnover"
    """
    prefix = GROUPS.get(group)
    if not prefix or not rows:
        return None

    last_close = _f(rows[-1].get("stck_clpr"))
    if last_close <= 0:
        return None

    s = _series(rows, prefix)
    n = len(s)

    # ── 이탈률 s_m 결정 ────────────────────────────────────────────
    if holdings_now and holdings_now > 0:
        h = _holdings_path(s, holdings_now)
        method = "holdings"
        exit_rate = []
        for i in range(n):
            base = h[i]
            exit_rate.append(min(1.0, s[i]["sell"] / base) if base > 0 else 0.0)
    elif shares_outstanding and shares_outstanding > 0:
        method = "market_turnover"
        exit_rate = [
            min(1.0, _i(r.get("acml_vol")) / shares_outstanding) for r in rows
        ]
    else:
        return None

    # ── 생존 가중치: 뒤에서부터 누적 곱 ─────────────────────────────
    # survive[i] = Π_{m>i} (1 − s_m)
    survive = [1.0] * n
    acc = 1.0
    for i in range(n - 1, -1, -1):
        survive[i] = acc
        acc *= 1.0 - exit_rate[i]

    num = 0.0
    den = 0.0
    used = 0
    buckets = defaultdict(float)
    for i in range(n):
        b, p = s[i]["buy"], s[i]["price"]
        if b <= 0 or p <= 0:
            continue
        w = b * survive[i]
        if w <= 0:
            continue
        num += w * p
        den += w
        used += 1
        buckets[p] += w

    if den <= 0 or used == 0:
        return None

    ref = num / den

    # ── 매물대: 가격을 12 구간으로 묶어 비중 ───────────────────────
    basis = []
    if buckets:
        lo, hi = min(buckets), max(buckets)
        if hi > lo:
            nb = 12
            step = (hi - lo) / nb
            agg = defaultdict(float)
            for p, w in buckets.items():
                k = min(nb - 1, int((p - lo) / step))
                agg[k] += w
            basis = [
                {
                    "price": round(lo + (k + 0.5) * step),
                    "weight": round(agg[k] / den * 100, 1),
                }
                for k in sorted(agg)
                if agg[k] / den * 100 >= 0.1
            ]
        else:
            basis = [{"price": round(lo), "weight": 100.0}]

    return {
        "reference": round(ref),
        "cgo": round((last_close - ref) / last_close * 100, 2),
        "coverage": used,
        "observations": n,
        "basis": basis,
        "method": method,
    }


# ─── 증분 상태 ──────────────────────────────────────────────────────
# 기준가격은 상태 두 개(num, den)만 들고 하루씩 갱신할 수 있다.
#     num_t = num_{t-1}·(1−s_t) + B_t·P_t
#     den_t = den_{t-1}·(1−s_t) + B_t
# 전체 이력을 다시 훑는 배치 계산과 결과가 정확히 같다(검증함).
# 덕분에 3 년치 원시 데이터를 보관할 필요가 없다.

# 매물대 분포도 같은 방식으로 감쇠시킨다. 가격 구간은 시간이 지나도 고정돼야
# 하므로 3% 로그 빈을 쓴다(빈 번호 = floor(ln P / ln 1.03)).
BIN_RATIO = 1.03
import math  # noqa: E402


def price_bin(p):
    return int(math.floor(math.log(p) / math.log(BIN_RATIO)))


def bin_price(k):
    return math.exp((k + 0.5) * math.log(BIN_RATIO))


def new_state():
    return {"n": 0.0, "d": 0.0, "b": {}}


def advance(state, exit_rate, buy_vol, buy_price):
    """하루치 갱신. exit_rate 만큼 기존 물량을 덜어내고 그날 매수분을 더한다."""
    keep = 1.0 - min(1.0, max(0.0, exit_rate))
    state["n"] *= keep
    state["d"] *= keep
    if state["b"]:
        if keep <= 0:
            state["b"] = {}
        else:
            for k in list(state["b"]):
                w = state["b"][k] * keep
                if w < 1e-9:
                    del state["b"][k]
                else:
                    state["b"][k] = w

    if buy_vol > 0 and buy_price > 0:
        state["n"] += buy_vol * buy_price
        state["d"] += buy_vol
        k = str(price_bin(buy_price))
        state["b"][k] = state["b"].get(k, 0.0) + buy_vol
    return state


def summarize(state, last_close, top_bins=12):
    """상태에서 기준가격 / CGO / 매물대를 뽑는다."""
    if not state or state["d"] <= 0 or last_close <= 0:
        return None
    ref = state["n"] / state["d"]
    total = sum(state["b"].values()) or 1.0
    bars = sorted(
        ({"price": round(bin_price(int(k))), "weight": round(v / total * 100, 1)}
         for k, v in state["b"].items() if v / total * 100 >= 0.5),
        key=lambda x: x["price"],
    )
    if len(bars) > top_bins:
        # 비중 큰 구간만 남기고 가격순 정렬 유지
        keep = sorted(bars, key=lambda x: -x["weight"])[:top_bins]
        bars = sorted(keep, key=lambda x: x["price"])
    return {
        "reference": round(ref),
        "cgo": round((last_close - ref) / last_close * 100, 2),
        "basis": bars,
    }


def exit_rate_for(group, row, series_item, holdings_at, shares_outstanding):
    """그날의 이탈률. 외국인은 실제 보유량, 기관은 시장 회전율."""
    if group == "foreign":
        return (series_item["sell"] / holdings_at) if holdings_at > 0 else 0.0
    if shares_outstanding > 0:
        return _i(row.get("acml_vol")) / shares_outstanding
    return 0.0


def build(rows, holdings_now=None, shares_outstanding=None):
    """외국인·기관 기준가격을 한 번에. kis_fetch 의 avg_cost 자리를 대체한다."""
    if not rows:
        return None
    price = _f(rows[-1].get("stck_clpr"))
    if price <= 0:
        return None

    out = {"price": price}
    f = reference_price(rows, "foreign", holdings_now=holdings_now)
    if f:
        out["foreign"] = f
    i = reference_price(rows, "institution", shares_outstanding=shares_outstanding)
    if i:
        out["institution"] = i
    return out if len(out) > 1 else None
