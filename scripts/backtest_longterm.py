"""
장기 보유(60일) 시그널 백테스트 — 연기금 + 가격 + 거래량 활용

학계/현업 근거:
- Jegadeesh-Titman (1993) momentum: 12개월 모멘텀, 60일 holding 효과
- Sias (2004) institutional herding: 기관 누적 매수 informed trading
- Bushee (1998) smart money: 장기 institutional flow가 미래 수익률 예측
- Baker-Bradley-Wurgler (2011) low-vol anomaly: 변동성 낮은 종목 outperform
- AQR Asness et al.: Value + Momentum + Quality composite

목표:
- 60거래일 보유, hit rate > 50%, t-stat > 3, 일평균 1+ 시그널

3개 후보:
- A. NPS-Confirmed Momentum: 가격 모멘텀 + 연기금 bps + 외인기관 동조 + 거래량
- B. Pension Steady Accumulation: 연기금 60일 양수일수 비율 + 낮은 변동성
- C. Smart Money Consensus: 외인+연기금 동시 매수 + 가격 모멘텀

실행:
  python scripts/backtest_longterm.py
"""

import json
import statistics
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TS_DIR = BASE_DIR / "scripts" / "backtest_data" / "timeseries"

sys.path.insert(0, str(BASE_DIR / "scripts"))
from backtest_signals import (  # noqa: E402
    safe_sum,
    _flow_bps,
    _mcap_at,
    _tv_surge,
)

# ───────────────────────────────────────────────────────────
# 설정
# ───────────────────────────────────────────────────────────

TC_ROUNDTRIP = 0.005  # 0.5% (장기 보유라 영향 적음)
FORWARD_WINDOW = 60   # 60거래일 = ~3개월
TRAIN_END_DATE = "2022-12-31"

REGIMES = [
    ("2016-2017", "2016-01-01", "2017-12-31"),
    ("2018-2019", "2018-01-01", "2019-12-31"),
    ("2020-2021", "2020-01-01", "2021-12-31"),
    ("2022", "2022-01-01", "2022-12-31"),
    ("2023-2024", "2023-01-01", "2024-12-31"),
    ("2025+", "2025-01-01", "2026-12-31"),
]


def load_timeseries():
    print("Loading timeseries...")
    t0 = time.time()
    files = [f for f in TS_DIR.glob("*.json") if f.stem != "_index"]
    data = {}
    for f in files:
        try:
            d = json.load(open(f, "r", encoding="utf-8"))
            data[d["ticker"]] = d
        except Exception:
            continue
    print(f"  Loaded {len(data)} tickers in {time.time() - t0:.1f}s")
    return data


# ───────────────────────────────────────────────────────────
# Helper
# ───────────────────────────────────────────────────────────

def price_mom(prices, idx, n):
    """N일 가격 모멘텀 (수익률)"""
    if idx < n or idx >= len(prices):
        return None
    p_now = prices[idx]
    p_past = prices[idx - n]
    if not p_now or not p_past or p_now <= 0 or p_past <= 0:
        return None
    return p_now / p_past - 1


def price_volatility(prices, idx, n=60):
    """N일 가격 변동성 (일일 수익률 std)"""
    if idx < n or idx >= len(prices):
        return None
    series = prices[idx - n:idx]
    rets = []
    for i in range(1, len(series)):
        if series[i] and series[i - 1] and series[i] > 0 and series[i - 1] > 0:
            rets.append(series[i] / series[i - 1] - 1)
    if len(rets) < n // 2:
        return None
    return statistics.stdev(rets) if len(rets) > 1 else None


def positive_days_ratio(arr, start, end):
    """[start, end) 범위에서 양수 비율"""
    if start < 0 or end > len(arr) or end <= start:
        return None
    window = arr[start:end]
    if not window:
        return None
    pos = sum(1 for v in window if v > 0)
    return pos / len(window)


def pct_rank(values, val):
    if len(values) <= 1:
        return 50
    below = sum(1 for v in values if v < val)
    return below / (len(values) - 1) * 100


# ───────────────────────────────────────────────────────────
# 전략 A: NPS-Confirmed Momentum
# ───────────────────────────────────────────────────────────

def score_strategy_a(data, idx, ctx=None):
    """
    A: 가격 모멘텀 + 연기금 매수 + 외인기관 동조 + 거래량 surge
    - 학계: Jegadeesh-Titman + Sias + Bushee
    """
    f = data.get("foreign", [])
    inst = data.get("inst", [])
    pension = data.get("pension", [])
    p = data.get("prices", [])
    if idx < 252 or idx >= len(f) or idx >= len(p):  # 12개월 + 여유
        return None

    mcap = _mcap_at(data, idx)
    if mcap is None or mcap < 50_000_000_000:  # 시총 500억+
        return None

    # 12-1 momentum (Jegadeesh-Titman: 12개월 - 가장 최근 1개월 skip)
    mom_12 = price_mom(p, idx - 20, 252 - 20)  # 1개월 전부터 12개월 전 사이
    if mom_12 is None or mom_12 <= 0:
        return None

    # 60일 가격 모멘텀
    mom_60 = price_mom(p, idx, 60)
    if mom_60 is None or mom_60 <= 0:
        return None

    # 연기금 60일 누적
    pen_60 = safe_sum(pension, idx - 60, idx)
    if pen_60 is None:
        return None
    pen_bps = _flow_bps(pen_60, mcap)
    if pen_bps is None or pen_bps < 5:  # 시총대비 5bp 이상
        return None

    # 외인+기관 60일 누적 (연기금 별도라 더해도 됨)
    f60 = safe_sum(f, idx - 60, idx)
    i60 = safe_sum(inst, idx - 60, idx)
    if f60 is None or i60 is None:
        return None
    fi_bps = _flow_bps(f60 + i60, mcap)
    if fi_bps is None or fi_bps < 0:  # 외인+기관도 양수
        return None

    # 거래량 surge
    surge = _tv_surge(data, idx, 20) or 0

    # Composite (raw values, 매일 cross-section에서 ranking)
    return {
        "mom_12": mom_12,
        "mom_60": mom_60,
        "pen_bps": pen_bps,
        "fi_bps": fi_bps,
        "surge": surge,
    }


def composite_a(sc, all_scores):
    """A 전략 composite: 백분위 가중 평균"""
    mom_12s = [s["mom_12"] for s in all_scores]
    mom_60s = [s["mom_60"] for s in all_scores]
    pen_bpss = [s["pen_bps"] for s in all_scores]
    fi_bpss = [s["fi_bps"] for s in all_scores]
    surges = [s["surge"] for s in all_scores]

    return (
        0.25 * pct_rank(mom_12s, sc["mom_12"])
        + 0.20 * pct_rank(mom_60s, sc["mom_60"])
        + 0.30 * pct_rank(pen_bpss, sc["pen_bps"])
        + 0.15 * pct_rank(fi_bpss, sc["fi_bps"])
        + 0.10 * pct_rank(surges, sc["surge"])
    )


# ───────────────────────────────────────────────────────────
# 전략 B: Pension Steady Accumulation + Low Vol
# ───────────────────────────────────────────────────────────

def score_strategy_b(data, idx, ctx=None):
    """
    B: 연기금 꾸준한 매수 + 낮은 변동성
    - 학계: Bushee long-term institutional + Baker-Bradley-Wurgler low-vol
    """
    pension = data.get("pension", [])
    p = data.get("prices", [])
    if idx < 60 or idx >= len(pension) or idx >= len(p):
        return None

    mcap = _mcap_at(data, idx)
    if mcap is None or mcap < 100_000_000_000:  # 시총 1000억+ (연기금 대상)
        return None

    # 연기금 60일 양수 일수 비율
    pen_pos_ratio = positive_days_ratio(pension, idx - 60, idx)
    if pen_pos_ratio is None or pen_pos_ratio < 0.55:  # 55% 이상 양수
        return None

    # 연기금 60일 누적
    pen_60 = safe_sum(pension, idx - 60, idx)
    pen_bps = _flow_bps(pen_60, mcap) if pen_60 is not None else None
    if pen_bps is None or pen_bps < 3:
        return None

    # 가격 변동성 (낮을수록 좋음)
    vol = price_volatility(p, idx, 60)
    if vol is None or vol > 0.05:  # 일일 5% 미만
        return None

    # 60일 모멘텀
    mom_60 = price_mom(p, idx, 60)
    if mom_60 is None or mom_60 < -0.10:  # -10% 미만 하락은 제외
        return None

    return {
        "pen_pos_ratio": pen_pos_ratio,
        "pen_bps": pen_bps,
        "vol_inv": 1 / vol,  # 변동성 역수 (낮을수록 높은 점수)
        "mom_60": mom_60,
    }


def composite_b(sc, all_scores):
    return (
        0.30 * pct_rank([s["pen_pos_ratio"] for s in all_scores], sc["pen_pos_ratio"])
        + 0.30 * pct_rank([s["pen_bps"] for s in all_scores], sc["pen_bps"])
        + 0.25 * pct_rank([s["vol_inv"] for s in all_scores], sc["vol_inv"])
        + 0.15 * pct_rank([s["mom_60"] for s in all_scores], sc["mom_60"])
    )


# ───────────────────────────────────────────────────────────
# 전략 C: Smart Money Consensus (외인+연기금 동조)
# ───────────────────────────────────────────────────────────

def score_strategy_c(data, idx, ctx=None):
    """
    C: 외인 + 연기금 둘 다 60일 매수 + 가격 양수 모멘텀
    - 학계: cross-institutional confirmation (Yan-Zhang)
    """
    f = data.get("foreign", [])
    pension = data.get("pension", [])
    p = data.get("prices", [])
    if idx < 60 or idx >= len(f) or idx >= len(p):
        return None

    mcap = _mcap_at(data, idx)
    if mcap is None or mcap < 50_000_000_000:
        return None

    # 외인 60일
    f60 = safe_sum(f, idx - 60, idx)
    f_bps = _flow_bps(f60, mcap) if f60 is not None else None
    if f_bps is None or f_bps < 5:  # 외인 5bp 이상
        return None

    # 연기금 60일
    pen_60 = safe_sum(pension, idx - 60, idx)
    pen_bps = _flow_bps(pen_60, mcap) if pen_60 is not None else None
    if pen_bps is None or pen_bps < 5:  # 연기금 5bp 이상
        return None

    # 가격 60일 모멘텀
    mom_60 = price_mom(p, idx, 60)
    if mom_60 is None or mom_60 < -0.05:
        return None

    # 가속도 (5일 / 20일 daily rate)
    f5 = safe_sum(f, idx - 5, idx)
    f20 = safe_sum(f, idx - 20, idx)
    accel = (f5 / 5) / (f20 / 20) if f20 and f20 > 0 else 0

    return {
        "f_bps": f_bps,
        "pen_bps": pen_bps,
        "mom_60": mom_60,
        "accel": max(accel, 0),
    }


def composite_c(sc, all_scores):
    return (
        0.30 * pct_rank([s["f_bps"] for s in all_scores], sc["f_bps"])
        + 0.30 * pct_rank([s["pen_bps"] for s in all_scores], sc["pen_bps"])
        + 0.20 * pct_rank([s["mom_60"] for s in all_scores], sc["mom_60"])
        + 0.20 * pct_rank([s["accel"] for s in all_scores], sc["accel"])
    )


# ───────────────────────────────────────────────────────────
# 전략 D: Pension Bottom Fishing (가격 횡보·하락 + 연기금 매수)
# ───────────────────────────────────────────────────────────

def score_strategy_d(data, idx, ctx=None):
    """
    D: 가격이 횡보/하락 중인데 연기금 누적 매수
    - 학계: Lakonishok-Shleifer-Vishny (1994) contrarian pension
    - 학계: Bushee (1998) long-term institutional informed bottom fishing
    """
    pension = data.get("pension", [])
    p = data.get("prices", [])
    if idx < 60 or idx >= len(pension) or idx >= len(p):
        return None

    mcap = _mcap_at(data, idx)
    if mcap is None or mcap < 50_000_000_000:
        return None

    # 가격 60일 모멘텀: -20% ~ +5% (횡보/하락만)
    mom_60 = price_mom(p, idx, 60)
    if mom_60 is None or mom_60 > 0.05 or mom_60 < -0.20:
        return None

    # 연기금 60일 누적 매수 ≥ 5bps
    pen_60 = safe_sum(pension, idx - 60, idx)
    if pen_60 is None or pen_60 <= 0:
        return None
    pen_bps = _flow_bps(pen_60, mcap)
    if pen_bps is None or pen_bps < 5:
        return None

    # 연기금 매수 일관성 (꾸준한 매수 vs 한 번에 큰 매수)
    pen_pos_ratio = positive_days_ratio(pension, idx - 60, idx)
    if pen_pos_ratio is None or pen_pos_ratio < 0.40:  # 40% 이상은 양수일
        return None

    # 거래량
    surge = _tv_surge(data, idx, 20) or 0

    return {
        "pen_bps": pen_bps,
        "pen_pos_ratio": pen_pos_ratio,
        "mom_60_neg": -mom_60,  # 하락 클수록 높은 점수 (contrarian)
        "surge": surge,
    }


def composite_d(sc, all_scores):
    return (
        0.40 * pct_rank([s["pen_bps"] for s in all_scores], sc["pen_bps"])
        + 0.25 * pct_rank([s["pen_pos_ratio"] for s in all_scores], sc["pen_pos_ratio"])
        + 0.25 * pct_rank([s["mom_60_neg"] for s in all_scores], sc["mom_60_neg"])
        + 0.10 * pct_rank([s["surge"] for s in all_scores], sc["surge"])
    )


# ───────────────────────────────────────────────────────────
# 전략 E: Pension vs Foreign Divergence (외국인 매도 + 연기금 매수)
# ───────────────────────────────────────────────────────────

def score_strategy_e(data, idx, ctx=None):
    """
    E: 외국인 매도 + 연기금 매수 = 도메스틱 smart money 정보 우위 시그널
    - 학계: Yan-Zhang (2009) institutional informed subset
    - 한국 시장: 외국인=글로벌 view, 연기금=로컬 정보 우위
    """
    f = data.get("foreign", [])
    pension = data.get("pension", [])
    p = data.get("prices", [])
    if idx < 60 or idx >= len(f) or idx >= len(p):
        return None

    mcap = _mcap_at(data, idx)
    if mcap is None or mcap < 50_000_000_000:
        return None

    # 연기금 60일 매수 ≥ 5bps
    pen_60 = safe_sum(pension, idx - 60, idx)
    if pen_60 is None or pen_60 <= 0:
        return None
    pen_bps = _flow_bps(pen_60, mcap)
    if pen_bps is None or pen_bps < 5:
        return None

    # 외국인 60일 매도 (음수)
    f60 = safe_sum(f, idx - 60, idx)
    if f60 is None or f60 >= 0:  # 외국인이 사고 있으면 divergence 아님
        return None
    f_bps = _flow_bps(f60, mcap)
    if f_bps is None or f_bps > -3:  # 시총대비 -3bps 이상 (확실한 매도)
        return None

    # 가격 60일 모멘텀 (참고): -15% ~ +10% (너무 극단적이지 않음)
    mom_60 = price_mom(p, idx, 60)
    if mom_60 is None or mom_60 < -0.15 or mom_60 > 0.10:
        return None

    # 연기금 매수 일관성
    pen_pos_ratio = positive_days_ratio(pension, idx - 60, idx)
    if pen_pos_ratio is None or pen_pos_ratio < 0.40:
        return None

    return {
        "pen_bps": pen_bps,
        "f_bps_abs": -f_bps,  # 외인 매도 클수록 divergence 강함 → 양수로 변환
        "pen_pos_ratio": pen_pos_ratio,
        "mom_60_neutral": -abs(mom_60),  # 횡보에 가까울수록 높은 점수
    }


def composite_e(sc, all_scores):
    return (
        0.35 * pct_rank([s["pen_bps"] for s in all_scores], sc["pen_bps"])
        + 0.30 * pct_rank([s["f_bps_abs"] for s in all_scores], sc["f_bps_abs"])
        + 0.20 * pct_rank([s["pen_pos_ratio"] for s in all_scores], sc["pen_pos_ratio"])
        + 0.15 * pct_rank([s["mom_60_neutral"] for s in all_scores], sc["mom_60_neutral"])
    )


# ───────────────────────────────────────────────────────────
# 전략 F: Pension-Driven Quality (A+E 융합, 더 strict)
# ───────────────────────────────────────────────────────────

def score_strategy_f(data, idx, ctx=None):
    """
    F: A (momentum + 연기금 매수) + E (divergence robust) 핵심 결합 + Quality filter
    - 연기금 강한 매수 + 일관성
    - 가격 안정적 상승 + 12-1 momentum
    - 외국인 강매도 제외 (또는 기관이 매수)
    - 낮은 변동성 + 시총 1000억+
    """
    f = data.get("foreign", [])
    inst = data.get("inst", [])
    pension = data.get("pension", [])
    p = data.get("prices", [])
    if idx < 252 or idx >= len(f) or idx >= len(p):
        return None

    mcap = _mcap_at(data, idx)
    if mcap is None or mcap < 100_000_000_000:  # 시총 1000억+ (NPS 대상)
        return None

    # 연기금 60일 매수 ≥ 5bps + 일관성 ≥ 0.50
    pen_60 = safe_sum(pension, idx - 60, idx)
    if pen_60 is None or pen_60 <= 0:
        return None
    pen_bps = _flow_bps(pen_60, mcap)
    if pen_bps is None or pen_bps < 5:
        return None
    pen_pos = positive_days_ratio(pension, idx - 60, idx)
    if pen_pos is None or pen_pos < 0.50:
        return None

    # 가격 12-1 momentum 양수
    mom_12 = price_mom(p, idx - 20, 252 - 20)
    if mom_12 is None or mom_12 <= 0:
        return None

    # 60일 모멘텀 -5% ~ +20% (양수 + 과열 제외)
    mom_60 = price_mom(p, idx, 60)
    if mom_60 is None or mom_60 < -0.05 or mom_60 > 0.20:
        return None

    # 외국인 강매도 제외 OR 기관 매수
    f60 = safe_sum(f, idx - 60, idx)
    i60 = safe_sum(inst, idx - 60, idx)
    if f60 is None or i60 is None:
        return None
    f_bps = _flow_bps(f60, mcap) or 0
    i_bps = _flow_bps(i60, mcap) or 0
    # 외인 매도 -5bps 이하(강매도)는 제외 OR 기관 매수 +3bps 이상이면 OK
    if f_bps < -5 and i_bps < 3:
        return None

    # 가격 변동성 낮음
    vol = price_volatility(p, idx, 60)
    if vol is None or vol > 0.035:  # 일일 3.5% 미만
        return None

    # 거래량 surge 양수 (활발한 거래)
    surge = _tv_surge(data, idx, 20) or 0
    if surge < 0:
        return None

    return {
        "pen_bps": pen_bps,
        "pen_pos": pen_pos,
        "mom_12": mom_12,
        "mom_60": mom_60,
        "f_bps_inv": -f_bps,  # 외인 매도 작을수록 좋음
        "i_bps": i_bps,
        "vol_inv": 1 / vol,
        "surge": surge,
    }


def composite_f(sc, all_scores):
    return (
        0.25 * pct_rank([s["pen_bps"] for s in all_scores], sc["pen_bps"])
        + 0.15 * pct_rank([s["pen_pos"] for s in all_scores], sc["pen_pos"])
        + 0.15 * pct_rank([s["mom_12"] for s in all_scores], sc["mom_12"])
        + 0.15 * pct_rank([s["mom_60"] for s in all_scores], sc["mom_60"])
        + 0.10 * pct_rank([s["f_bps_inv"] for s in all_scores], sc["f_bps_inv"])
        + 0.10 * pct_rank([s["vol_inv"] for s in all_scores], sc["vol_inv"])
        + 0.10 * pct_rank([s["surge"] for s in all_scores], sc["surge"])
    )


# ───────────────────────────────────────────────────────────
# Backtest engine
# ───────────────────────────────────────────────────────────

def run_backtest(timeseries, score_func, composite_func, top_n=2, label="STRATEGY", no_reentry_days=60):
    """매 영업일마다 top-N 종목 → 60일 forward return.

    no_reentry_days: 같은 종목 재진입 금지 기간 (영업일).
        0이면 매일 top-N 그대로 (overlapping bias 있음).
        60이면 진정한 "신규 시그널"만 (학계 표준).
    """
    all_dates = set()
    for d in timeseries.values():
        all_dates.update(d.get("dates", []))
    all_dates = sorted(all_dates)
    eval_dates = all_dates[:-FORWARD_WINDOW] if len(all_dates) > FORWARD_WINDOW else []

    results = []
    t0 = time.time()
    n_dates_with_signal = 0
    last_entry_date_idx = {}  # ticker -> 마지막 entry date의 index in eval_dates

    for di, date in enumerate(eval_dates):
        # 모든 종목 점수 계산
        scored = {}
        for ticker, data in timeseries.items():
            try:
                idx = data["dates"].index(date)
            except ValueError:
                continue
            s = score_func(data, idx)
            if s is not None:
                scored[ticker] = (s, idx)

        if not scored:
            continue

        all_score_dicts = [s for s, _ in scored.values()]
        ranked = []
        for ticker, (s, idx) in scored.items():
            comp = composite_func(s, all_score_dicts)
            ranked.append((ticker, comp, idx))
        ranked.sort(key=lambda x: -x[1])

        n_dates_with_signal += 1
        taken = 0
        for ticker, comp, idx in ranked:
            if taken >= top_n:
                break
            # no-re-entry rule: 최근 N일 내 진입했으면 skip
            last_di = last_entry_date_idx.get(ticker)
            if last_di is not None and (di - last_di) < no_reentry_days:
                continue

            data = timeseries[ticker]
            prices = data.get("prices", [])
            if idx >= len(prices) or not prices[idx] or prices[idx] <= 0:
                continue
            p_now = prices[idx]
            fi = idx + FORWARD_WINDOW
            if fi < len(prices) and prices[fi] and prices[fi] > 0:
                ret = prices[fi] / p_now - 1
                results.append({"date": date, "ticker": ticker, "score": comp, "ret60": ret})
                last_entry_date_idx[ticker] = di
                taken += 1

    elapsed = time.time() - t0
    print(f"  [{label}] {len(results)} events / {n_dates_with_signal} signal days ({elapsed:.1f}s)")
    return results, n_dates_with_signal


# ───────────────────────────────────────────────────────────
# Metrics
# ───────────────────────────────────────────────────────────

def compute_metrics(results):
    valid = [r["ret60"] for r in results if r.get("ret60") is not None]
    if not valid:
        return None
    n = len(valid)
    avg = statistics.mean(valid)
    median = statistics.median(valid)
    hit = sum(1 for r in valid if r > 0) / n
    std = statistics.stdev(valid) if n > 1 else 0
    avg_tc = avg - TC_ROUNDTRIP
    # Annualized Sharpe ≈ avg/std × sqrt(250/60) = sqrt(4.17) ≈ 2.04
    sharpe = (avg / std) * ((250 / FORWARD_WINDOW) ** 0.5) if std > 0 else 0
    sharpe_tc = (avg_tc / std) * ((250 / FORWARD_WINDOW) ** 0.5) if std > 0 else 0
    t_stat = (avg / (std / (n ** 0.5))) if std > 0 else 0
    return {"n": n, "avg": avg, "median": median, "hit": hit, "std": std,
            "avg_tc": avg_tc, "sharpe": sharpe, "sharpe_tc": sharpe_tc, "t_stat": t_stat}


def regime_split(results):
    out = {}
    for name, s, e in REGIMES:
        sub = [r for r in results if s <= r["date"] <= e]
        out[name] = compute_metrics(sub)
    return out


def train_test(results):
    train = [r for r in results if r["date"] <= TRAIN_END_DATE]
    test = [r for r in results if r["date"] > TRAIN_END_DATE]
    return compute_metrics(train), compute_metrics(test)


def fmt(v):
    return f"{v*100:+6.2f}%" if v is not None else "  -  "


def report(name, results, n_dates):
    print(f"\n{'=' * 60}")
    print(f"  {name}")
    print(f"{'=' * 60}")
    m = compute_metrics(results)
    if not m:
        print("  NO RESULTS")
        return
    avg_per_day = m["n"] / n_dates if n_dates > 0 else 0
    print(f"\n  Events: {m['n']:,} / Signal days: {n_dates:,} / Avg: {avg_per_day:.2f}/day")
    print(f"  60d avg:        {fmt(m['avg'])}")
    print(f"  60d avg (TC):   {fmt(m['avg_tc'])}")
    print(f"  60d median:     {fmt(m['median'])}")
    print(f"  Hit rate:       {m['hit']*100:5.1f}%")
    print(f"  Std:            {fmt(m['std'])}")
    print(f"  Sharpe (ann):   {m['sharpe']:6.2f}")
    print(f"  Sharpe TC:      {m['sharpe_tc']:6.2f}")
    print(f"  t-stat:         {m['t_stat']:6.2f}")

    tr, te = train_test(results)
    if tr and te:
        print(f"\n  Walk-forward (Train <= {TRAIN_END_DATE}):")
        print(f"    Train: avg={fmt(tr['avg'])} hit={tr['hit']*100:5.1f}% t={tr['t_stat']:5.2f}")
        print(f"    Test : avg={fmt(te['avg'])} hit={te['hit']*100:5.1f}% t={te['t_stat']:5.2f}")

    rs = regime_split(results)
    print(f"\n  Regime split:")
    for rname, rm in rs.items():
        if rm:
            print(f"    [{rname:10s}] N={rm['n']:>5d} avg={fmt(rm['avg'])} hit={rm['hit']*100:5.1f}% t={rm['t_stat']:5.2f}")

    target_check = []
    target_check.append(("[OK]" if m["hit"] > 0.50 else "[NO]") + f" hit {m['hit']*100:.1f}%")
    target_check.append(("[OK]" if m["t_stat"] > 3 else "[NO]") + f" t-stat {m['t_stat']:.2f}")
    target_check.append(("[OK]" if avg_per_day >= 1 else "[NO]") + f" avg {avg_per_day:.2f}/day")
    print(f"\n  Targets: {' | '.join(target_check)}")


def main():
    ts = load_timeseries()

    # No-re-entry 60일 적용해서 진짜 alpha 검증
    strategies = [
        ("A: NPS Momentum (top-2, no-reentry)", score_strategy_a, composite_a, 2),
        ("A: NPS Momentum (top-5, no-reentry)", score_strategy_a, composite_a, 5),
        ("E: Divergence (top-2, no-reentry)", score_strategy_e, composite_e, 2),
        ("E: Divergence (top-5, no-reentry)", score_strategy_e, composite_e, 5),
    ]

    all_results = {}
    for label, score_fn, comp_fn, top_n in strategies:
        print(f"\n>>> Running {label} (top-{top_n})")
        results, n_dates = run_backtest(ts, score_fn, comp_fn, top_n=top_n, label=label)
        all_results[label] = (results, n_dates)
        report(label, results, n_dates)

    # 비교 요약
    print(f"\n\n{'=' * 60}")
    print("  SUMMARY")
    print(f"{'=' * 60}")
    print(f"  {'Strategy':<40s} {'Hit':>8s} {'t-stat':>8s} {'TC adj':>10s} {'N/day':>8s}")
    for label, (results, n_dates) in all_results.items():
        m = compute_metrics(results)
        if m and n_dates > 0:
            avg_per_day = m["n"] / n_dates
            print(f"  {label:<40s} {m['hit']*100:>7.1f}% {m['t_stat']:>8.2f} {fmt(m['avg_tc'])} {avg_per_day:>7.2f}")


if __name__ == "__main__":
    main()
