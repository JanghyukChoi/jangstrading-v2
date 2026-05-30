"""
시그널 백테스트 엔진 — Lite Quant

입력: scripts/backtest_data/timeseries/*.json (10년 시계열, 3,234 종목)
출력: 콘솔 — 시그널 후보별 성과 지표 표

처리 흐름:
1. 모든 timeseries 메모리 로드
2. 백테스트 기간 내 매 영업일마다 시그널 발생 종목 식별
3. 각 시그널 종목의 forward return (+5일, +20일) 측정
4. 지표 계산: 평균 수익률, 적중률, Sharpe, IC, TC 차감, regime split

실행:
  python scripts/backtest_signals.py
  python scripts/backtest_signals.py --signal buy_reversal --candidate v1
"""

import argparse
import json
import statistics
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TS_DIR = BASE_DIR / "scripts" / "backtest_data" / "timeseries"

# 백테스트 설정
TC_ROUNDTRIP = 0.005  # 0.5% (한국 retail: 수수료 + 매도세 + 슬리피지)
FORWARD_WINDOWS = [5, 20]  # 영업일

# 시장 국면 정의 (영업일 기준 인덱스로 대략 분할)
# 우리 데이터: 2016-02-19 ~ 2026-05-29
# 분할: bull / bear / sideways 대략
# 실제로는 KOSPI 수익률로 자동 분류해야 함. 단순화로 시기별 분류.
REGIMES = [
    ("2016-2017", "2016-01-01", "2017-12-31"),
    ("2018-2019", "2018-01-01", "2019-12-31"),
    ("2020-2021", "2020-01-01", "2021-12-31"),
    ("2022", "2022-01-01", "2022-12-31"),
    ("2023-2024", "2023-01-01", "2024-12-31"),
    ("2025+", "2025-01-01", "2026-12-31"),
]

# Train/Test split (walk-forward)
TRAIN_END_DATE = "2022-12-31"  # 이전 = train, 이후 = test


# ───────────────────────────────────────────────────────────
# Data Loading
# ───────────────────────────────────────────────────────────

def load_all_timeseries():
    """모든 종목 timeseries 메모리 로드. ticker -> data"""
    print("Loading timeseries...")
    t0 = time.time()
    files = [f for f in TS_DIR.glob("*.json") if f.stem != "_index"]
    data = {}
    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fp:
                d = json.load(fp)
            ticker = d["ticker"]
            data[ticker] = d
        except Exception:
            continue
    print(f"  Loaded {len(data)} tickers in {time.time() - t0:.1f}s")
    return data


# ───────────────────────────────────────────────────────────
# Component Helpers
# ───────────────────────────────────────────────────────────

def safe_sum(arr, start, end):
    """배열 인덱스 범위 합산 (out-of-bounds 안전)"""
    if start < 0 or end > len(arr):
        return None
    return sum(arr[start:end])


def rolling_normalize(values, end_idx, window=252):
    """그 종목 historical N일 평균 절대값으로 정규화 기준 계산"""
    start = max(0, end_idx - window)
    history = values[start:end_idx]
    if len(history) < 60:
        return None
    abs_avg = sum(abs(x) for x in history) / len(history)
    return abs_avg if abs_avg > 0 else None


# ───────────────────────────────────────────────────────────
# Signal Definitions
# ───────────────────────────────────────────────────────────

def signal_buy_reversal_v1(data, idx):
    """매수전환 V1 — Mean Reversion (외인)"""
    f = data.get("foreign", [])
    if idx < 60 or idx >= len(f):
        return None
    f60 = safe_sum(f, idx - 60, idx)
    f5 = safe_sum(f, idx - 5, idx)
    if f60 is None or f5 is None:
        return None
    if f60 >= 0 or f5 <= 0:
        return None
    norm = rolling_normalize(f, idx, window=252)
    if norm is None:
        return None
    return (abs(f60) / (norm * 60)) * 0.5 + (f5 / (norm * 5)) * 0.5


def signal_sell_reversal_v1(data, idx):
    """매도전환 V1 — Mean Reversion 대칭 (overbought → 매도 전환)

    가설: 60일 외인 매수 누적 후 5일 매도 전환 = 단기 하락
    Forward return이 음수일수록 시그널 적중
    """
    f = data.get("foreign", [])
    if idx < 60 or idx >= len(f):
        return None
    f60 = safe_sum(f, idx - 60, idx)
    f5 = safe_sum(f, idx - 5, idx)
    if f60 is None or f5 is None:
        return None
    if f60 <= 0 or f5 >= 0:  # overbought + sell-reversal 조건
        return None
    norm = rolling_normalize(f, idx, window=252)
    if norm is None:
        return None
    overbought = f60 / (norm * 60)
    reversal = abs(f5) / (norm * 5)
    return overbought * 0.5 + reversal * 0.5


def signal_leader_v1(data, idx):
    """주도주 V1 — Cross-sectional momentum + flow strength

    Note: V1은 sector 정보 없음 — 시장 전체 cross-section 기준
    가설: 가격 + flow 모두 강한 종목 = 주도주, outperform 지속

    Components:
    - Price momentum (60일 수익률)
    - Flow strength (60일 누적 외인+기관)
    - Acceleration (5일 flow / 20일 flow * 4)
    """
    f = data.get("foreign", [])
    i = data.get("inst", [])
    p = data.get("prices", [])
    if idx < 60 or idx >= len(f) or idx >= len(p):
        return None

    # Price momentum
    if idx - 60 < 0 or p[idx - 60] is None or p[idx - 60] <= 0:
        return None
    p_now = p[idx]
    if p_now is None or p_now <= 0:
        return None
    price_mom = p_now / p[idx - 60] - 1

    # Flow strength (외인+기관)
    f60 = safe_sum(f, idx - 60, idx)
    i60 = safe_sum(i, idx - 60, idx)
    if f60 is None or i60 is None:
        return None
    combined60 = f60 + i60
    if combined60 <= 0:  # 매수세 있는 종목만
        return None

    # 정규화 (외인+기관 합산 기준)
    norm_f = rolling_normalize(f, idx, window=252)
    norm_i = rolling_normalize(i, idx, window=252)
    if norm_f is None or norm_i is None:
        return None
    norm = norm_f + norm_i
    if norm <= 0:
        return None
    flow_strength = combined60 / (norm * 60)

    # Acceleration
    f5 = safe_sum(f, idx - 5, idx)
    i5 = safe_sum(i, idx - 5, idx)
    f20 = safe_sum(f, idx - 20, idx)
    i20 = safe_sum(i, idx - 20, idx)
    if any(x is None for x in [f5, i5, f20, i20]):
        return None
    combined5 = f5 + i5
    combined20 = f20 + i20
    if combined20 == 0:
        accel = 1
    else:
        accel = (combined5 / 5) / (combined20 / 20)  # daily rate ratio

    # Composite (가격 + flow + 가속도)
    return price_mom * 0.4 + flow_strength * 0.4 + max(accel, 0) * 0.2


# ───────────────────────────────────────────────────────────
# V2 Signals — Multi-investor + Price filter + Regime
# ───────────────────────────────────────────────────────────

def _rolling_price_avg(prices, end_idx, window=60):
    """N일 가격 평균 (0 제외)"""
    if end_idx < window:
        return None
    arr = [p for p in prices[end_idx - window:end_idx] if p and p > 0]
    if len(arr) < window // 2:  # 데이터 부족
        return None
    return sum(arr) / len(arr)


def signal_buy_reversal_v2(data, idx, ctx=None):
    """매수전환 V2 — Multi-investor + Price oversold + Regime filter

    Conditions:
    - 외인 60일 누적 < 0
    - 외인 5일 누적 > 0 (reversal)
    - 기관 5일 누적 > 0 (confirmation)
    - 가격 < 60일 평균 (price oversold)
    - KOSPI 60일 모멘텀 > -5% (regime filter)
    """
    f = data.get("foreign", [])
    inst = data.get("inst", [])
    p = data.get("prices", [])
    if idx < 60 or idx >= len(f) or idx >= len(p):
        return None

    # Regime filter
    if ctx and ctx.get("kospi_mom60") is not None and ctx["kospi_mom60"] < -0.05:
        return None

    f60 = safe_sum(f, idx - 60, idx)
    f5 = safe_sum(f, idx - 5, idx)
    i5 = safe_sum(inst, idx - 5, idx)
    if any(x is None for x in [f60, f5, i5]):
        return None

    if f60 >= 0 or f5 <= 0 or i5 <= 0:
        return None

    # Price oversold
    p_now = p[idx]
    if not p_now or p_now <= 0:
        return None
    p_avg = _rolling_price_avg(p, idx, 60)
    if p_avg is None or p_now >= p_avg:  # 60일 평균 위면 oversold 아님
        return None

    norm_f = rolling_normalize(f, idx, 252)
    norm_i = rolling_normalize(inst, idx, 252)
    if norm_f is None or norm_i is None:
        return None

    oversold = abs(f60) / (norm_f * 60)
    rev_f = f5 / (norm_f * 5)
    rev_i = i5 / (norm_i * 5)
    price_below = 1 - p_now / p_avg  # 60일 평균 대비 얼마나 낮은지

    return oversold * 0.4 + (rev_f + rev_i) / 2 * 0.4 + min(price_below * 5, 1) * 0.2


def signal_sell_reversal_v2(data, idx, ctx=None):
    """매도전환 V2 — V1과 정의 자체 다름

    V1 문제: '매수 후 매도'가 사실 short 신호로 작동 안 함
    V2 가설: '외인+기관 동시 매도 + 가격 신고가 근처' = 진짜 도망 신호

    Conditions:
    - 외인 5일 누적 < 0 + 기관 5일 누적 < 0 (동시 매도)
    - 가격 > 60일 평균 (overbought)
    - 외인 60일 누적 > 0 (이전엔 매수했음 → 전환)
    """
    f = data.get("foreign", [])
    inst = data.get("inst", [])
    p = data.get("prices", [])
    if idx < 60 or idx >= len(f) or idx >= len(p):
        return None

    if ctx and ctx.get("kospi_mom60") is not None and ctx["kospi_mom60"] > 0.10:
        return None  # 강세장에선 short 시그널 끔

    f60 = safe_sum(f, idx - 60, idx)
    f5 = safe_sum(f, idx - 5, idx)
    i5 = safe_sum(inst, idx - 5, idx)
    if any(x is None for x in [f60, f5, i5]):
        return None

    if f60 <= 0 or f5 >= 0 or i5 >= 0:
        return None

    p_now = p[idx]
    if not p_now or p_now <= 0:
        return None
    p_avg = _rolling_price_avg(p, idx, 60)
    if p_avg is None or p_now <= p_avg:
        return None

    norm_f = rolling_normalize(f, idx, 252)
    norm_i = rolling_normalize(inst, idx, 252)
    if norm_f is None or norm_i is None:
        return None

    overbought = f60 / (norm_f * 60)
    sell_f = abs(f5) / (norm_f * 5)
    sell_i = abs(i5) / (norm_i * 5)
    price_above = p_now / p_avg - 1

    return overbought * 0.4 + (sell_f + sell_i) / 2 * 0.4 + min(price_above * 5, 1) * 0.2


def signal_leader_v2(data, idx, ctx=None):
    """주도주 V2 — Multi-investor 동조 + 더 엄격한 momentum + Regime filter"""
    f = data.get("foreign", [])
    inst = data.get("inst", [])
    p = data.get("prices", [])
    if idx < 60 or idx >= len(f) or idx >= len(p):
        return None

    # Regime: bear market에선 주도주 의미 약함
    if ctx and ctx.get("kospi_mom60") is not None and ctx["kospi_mom60"] < -0.05:
        return None

    # Price momentum
    if idx - 60 < 0 or p[idx - 60] is None or p[idx - 60] <= 0:
        return None
    p_now = p[idx]
    if not p_now or p_now <= 0:
        return None
    price_mom = p_now / p[idx - 60] - 1
    if price_mom <= 0:  # 가격이 상승해야 주도주
        return None

    # Multi-investor flow strength
    f60 = safe_sum(f, idx - 60, idx)
    i60 = safe_sum(inst, idx - 60, idx)
    if f60 is None or i60 is None:
        return None
    if f60 <= 0 or i60 <= 0:  # 외인 + 기관 둘 다 매수 필요
        return None

    norm_f = rolling_normalize(f, idx, 252)
    norm_i = rolling_normalize(inst, idx, 252)
    if norm_f is None or norm_i is None:
        return None
    f_strength = f60 / (norm_f * 60)
    i_strength = i60 / (norm_i * 60)

    # Acceleration
    f5 = safe_sum(f, idx - 5, idx)
    i5 = safe_sum(inst, idx - 5, idx)
    f20 = safe_sum(f, idx - 20, idx)
    i20 = safe_sum(inst, idx - 20, idx)
    if any(x is None for x in [f5, i5, f20, i20]):
        return None
    f_accel = (f5 / 5) / (f20 / 20) if f20 > 0 else 0
    i_accel = (i5 / 5) / (i20 / 20) if i20 > 0 else 0
    accel = (max(f_accel, 0) + max(i_accel, 0)) / 2

    return price_mom * 0.35 + (f_strength + i_strength) / 2 * 0.4 + min(accel, 3) * 0.25


def signal_accumulation_v2(data, idx, ctx=None):
    """집중매수 V2 — 외인+기관 동조 + 가속도 + price uptrend + Regime"""
    f = data.get("foreign", [])
    inst = data.get("inst", [])
    p = data.get("prices", [])
    if idx < 20 or idx >= len(f) or idx >= len(p):
        return None

    if ctx and ctx.get("kospi_mom60") is not None and ctx["kospi_mom60"] < -0.05:
        return None

    f20 = safe_sum(f, idx - 20, idx)
    i20 = safe_sum(inst, idx - 20, idx)
    f5 = safe_sum(f, idx - 5, idx)
    i5 = safe_sum(inst, idx - 5, idx)
    if any(x is None for x in [f20, i20, f5, i5]):
        return None

    if f20 <= 0 or i20 <= 0 or f5 <= 0 or i5 <= 0:
        return None

    # Price uptrend (60일 평균 위)
    p_now = p[idx]
    if not p_now or p_now <= 0:
        return None
    p_avg = _rolling_price_avg(p, idx, 60)
    if p_avg is None or p_now <= p_avg:
        return None

    norm_f = rolling_normalize(f, idx, 252)
    norm_i = rolling_normalize(inst, idx, 252)
    if norm_f is None or norm_i is None:
        return None
    f_str = f20 / (norm_f * 20)
    i_str = i20 / (norm_i * 20)

    f_accel = (f5 / 5) / (f20 / 20) if f20 > 0 else 0
    i_accel = (i5 / 5) / (i20 / 20) if i20 > 0 else 0
    accel = (f_accel + i_accel) / 2
    if accel < 1:
        return None

    price_above = p_now / p_avg - 1
    return (f_str + i_str) * 0.4 + accel * 0.35 + min(price_above * 3, 1) * 0.25


# ───────────────────────────────────────────────────────────
# V3 Signals — Market-cap normalized + Volume surge + Regime
# ───────────────────────────────────────────────────────────
#
# 핵심 아이디어:
#  - foreign/inst 값(백만원)을 시가총액(원) 대비 basis points로 환산
#    → "시총대비 매수강도": 대형주/소형주 cross-sectional 비교 가능
#  - 거래대금 surge: today_tv / 20일 평균 tv → 평소 대비 거래량
#  - 절대값 임계값 폐기, 시총대비 % 임계값 사용
#  - foreign_1d/inst_1d 단위: 백만원 → 원 환산 시 × 1_000_000
#
# bps_to_mcap = (foreign_5d_백만원 × 1_000_000) / market_cap_원 × 10_000
#             = foreign_5d × 10_000 / market_cap (백만원 단위 그대로 쓰면)

UNIT_BP_TO_MCAP = 10_000_000_000  # 백만원→원(×1e6) /market_cap_원 ×10000bps = ×1e10


def _mcap_at(data, idx):
    """idx 시점의 시가총액(원). 0 이면 None"""
    mc_arr = data.get("market_cap", [])
    if idx >= len(mc_arr):
        return None
    mc = mc_arr[idx]
    return mc if mc and mc > 0 else None


def _tv_surge(data, idx, window=20):
    """idx 시점 거래대금 / 직전 window일 평균 - 1 (음수면 평소보다 적음)"""
    tv_arr = data.get("trade_value", [])
    if idx >= len(tv_arr) or idx < window:
        return None
    today = tv_arr[idx]
    if not today or today <= 0:
        return None
    past = [v for v in tv_arr[idx - window:idx] if v and v > 0]
    if len(past) < window // 2:
        return None
    avg = sum(past) / len(past)
    if avg <= 0:
        return None
    return today / avg - 1


def _flow_bps(flow_sum_million, mcap_won):
    """순매수(백만원) → 시총대비 bps. mcap_won은 원 단위"""
    if mcap_won is None or mcap_won <= 0:
        return None
    return flow_sum_million * UNIT_BP_TO_MCAP / mcap_won


def signal_buy_reversal_v3(data, idx, ctx=None):
    """매수전환 V3 — 시총대비 bps + 거래량 surge + multi-investor + regime

    Conditions:
    - 외인 60일 누적 < 0 (시총대비 < -50bps)
    - 외인 5일 + 기관 5일 > 0 (동시 reversal)
    - 가격 < 60일 평균 (oversold)
    - 거래대금 surge > 20% (반등에 거래 동반)
    - KOSPI mom60 >= -5%
    """
    f = data.get("foreign", [])
    inst = data.get("inst", [])
    p = data.get("prices", [])
    if idx < 60 or idx >= len(f) or idx >= len(p):
        return None

    # regime filter 제거 (모든 국면에서 시그널 표시)

    mcap = _mcap_at(data, idx)
    if mcap is None or mcap < 50_000_000_000:  # 시총 500억 미만은 노이즈
        return None

    f60 = safe_sum(f, idx - 60, idx)
    f5 = safe_sum(f, idx - 5, idx)
    i5 = safe_sum(inst, idx - 5, idx)
    if any(x is None for x in [f60, f5, i5]):
        return None

    f60_bps = _flow_bps(f60, mcap)
    f5_bps = _flow_bps(f5, mcap)
    i5_bps = _flow_bps(i5, mcap)
    if f60_bps is None or f5_bps is None or i5_bps is None:
        return None

    # Mean-reversion: 60일 oversold, 5일 동시 매수
    if f60_bps >= -15:  # -15bps 미만 oversold (완화: -30 → -15)
        return None
    if f5_bps <= 2 or i5_bps <= 2:  # 둘 다 +2bps (완화: +5 → +2)
        return None

    # Price oversold
    p_now = p[idx]
    if not p_now or p_now <= 0:
        return None
    p_avg = _rolling_price_avg(p, idx, 60)
    if p_avg is None or p_now >= p_avg:  # 60일 평균보다 낮음 (완화: 0.97 → 1.0)
        return None

    # Volume surge confirmation
    surge = _tv_surge(data, idx, 20)
    if surge is None or surge < 0.05:  # +5% (완화: +20 → +5)
        return None

    # Composite score
    oversold_score = min(abs(f60_bps) / 100, 3)  # cap at -300bps
    reversal_score = (f5_bps + i5_bps) / 20  # 합 40bps면 score 2
    price_below_score = min((1 - p_now / p_avg) * 10, 2)
    vol_score = min(surge, 2)

    return oversold_score * 0.30 + reversal_score * 0.35 + price_below_score * 0.20 + vol_score * 0.15


def signal_sell_reversal_v3(data, idx, ctx=None):
    """매도전환 V3 — bps 기준 overbought + 동시 매도 + 가격 신고가 + 거래량 surge"""
    f = data.get("foreign", [])
    inst = data.get("inst", [])
    p = data.get("prices", [])
    if idx < 60 or idx >= len(f) or idx >= len(p):
        return None

    # regime filter 제거 (모든 국면에서 시그널 표시)

    mcap = _mcap_at(data, idx)
    if mcap is None or mcap < 50_000_000_000:
        return None

    f60 = safe_sum(f, idx - 60, idx)
    f5 = safe_sum(f, idx - 5, idx)
    i5 = safe_sum(inst, idx - 5, idx)
    if any(x is None for x in [f60, f5, i5]):
        return None

    f60_bps = _flow_bps(f60, mcap)
    f5_bps = _flow_bps(f5, mcap)
    i5_bps = _flow_bps(i5, mcap)
    if f60_bps is None or f5_bps is None or i5_bps is None:
        return None

    if f60_bps <= 15:  # 60일 +15bps (완화: +30 → +15)
        return None
    if f5_bps >= -2 or i5_bps >= -2:  # 둘 다 -2bps (완화: -5 → -2)
        return None

    p_now = p[idx]
    if not p_now or p_now <= 0:
        return None
    p_avg = _rolling_price_avg(p, idx, 60)
    if p_avg is None or p_now <= p_avg:  # 60일 평균보다 위 (완화: 1.03 → 1.0)
        return None

    surge = _tv_surge(data, idx, 20)
    if surge is None or surge < 0.05:  # +5% (완화: +20 → +5)
        return None

    overbought_score = min(f60_bps / 100, 3)
    sell_score = (abs(f5_bps) + abs(i5_bps)) / 20
    price_above_score = min((p_now / p_avg - 1) * 10, 2)
    vol_score = min(surge, 2)

    return overbought_score * 0.30 + sell_score * 0.35 + price_above_score * 0.20 + vol_score * 0.15


def signal_leader_v3(data, idx, ctx=None):
    """주도주 V3 — bps 기반 multi-investor + price momentum + acceleration"""
    f = data.get("foreign", [])
    inst = data.get("inst", [])
    p = data.get("prices", [])
    if idx < 60 or idx >= len(f) or idx >= len(p):
        return None

    # regime filter 제거 (모든 국면에서 시그널 표시)

    mcap = _mcap_at(data, idx)
    if mcap is None or mcap < 100_000_000_000:  # 주도주는 시총 1000억 이상만
        return None

    p_now = p[idx]
    if not p_now or p_now <= 0:
        return None
    p_60 = p[idx - 60] if idx - 60 >= 0 else None
    if not p_60 or p_60 <= 0:
        return None
    price_mom = p_now / p_60 - 1
    if price_mom < 0.05:  # 60일 +5% 이상
        return None

    f60 = safe_sum(f, idx - 60, idx)
    i60 = safe_sum(inst, idx - 60, idx)
    if f60 is None or i60 is None:
        return None
    f60_bps = _flow_bps(f60, mcap)
    i60_bps = _flow_bps(i60, mcap)
    if f60_bps is None or i60_bps is None:
        return None
    if f60_bps <= 20 or i60_bps <= 20:  # 둘 다 +20bps 이상
        return None

    # Acceleration
    f5 = safe_sum(f, idx - 5, idx)
    i5 = safe_sum(inst, idx - 5, idx)
    f20 = safe_sum(f, idx - 20, idx)
    i20 = safe_sum(inst, idx - 20, idx)
    if any(x is None for x in [f5, i5, f20, i20]):
        return None

    f_accel = (f5 / 5) / (f20 / 20) if f20 > 0 else 0
    i_accel = (i5 / 5) / (i20 / 20) if i20 > 0 else 0
    accel = (max(f_accel, 0) + max(i_accel, 0)) / 2

    surge = _tv_surge(data, idx, 20)
    vol_score = min(max(surge or 0, 0), 2)

    mom_score = min(price_mom * 5, 3)
    flow_score = (f60_bps + i60_bps) / 100  # 합 200bps면 2점
    accel_score = min(accel, 3)

    return mom_score * 0.30 + flow_score * 0.35 + accel_score * 0.20 + vol_score * 0.15


def signal_accumulation_v3(data, idx, ctx=None):
    """집중매수 V3 — 외인+기관 20일 동시 매수 (bps) + 가속도 + 가격 uptrend + 거래량"""
    f = data.get("foreign", [])
    inst = data.get("inst", [])
    p = data.get("prices", [])
    if idx < 60 or idx >= len(f) or idx >= len(p):
        return None

    # regime filter 제거 (모든 국면에서 시그널 표시)

    mcap = _mcap_at(data, idx)
    if mcap is None or mcap < 50_000_000_000:
        return None

    f20 = safe_sum(f, idx - 20, idx)
    i20 = safe_sum(inst, idx - 20, idx)
    f5 = safe_sum(f, idx - 5, idx)
    i5 = safe_sum(inst, idx - 5, idx)
    if any(x is None for x in [f20, i20, f5, i5]):
        return None

    f20_bps = _flow_bps(f20, mcap)
    i20_bps = _flow_bps(i20, mcap)
    f5_bps = _flow_bps(f5, mcap)
    i5_bps = _flow_bps(i5, mcap)
    if any(x is None for x in [f20_bps, i20_bps, f5_bps, i5_bps]):
        return None

    # 20일 동시 매수, 5일도 양자 + 이상
    if f20_bps <= 10 or i20_bps <= 10:
        return None
    if f5_bps <= 0 or i5_bps <= 0:
        return None

    # Price uptrend
    p_now = p[idx]
    if not p_now or p_now <= 0:
        return None
    p_avg = _rolling_price_avg(p, idx, 60)
    if p_avg is None or p_now <= p_avg:
        return None

    # Acceleration
    f_accel = (f5 / 5) / (f20 / 20) if f20 > 0 else 0
    i_accel = (i5 / 5) / (i20 / 20) if i20 > 0 else 0
    accel = (f_accel + i_accel) / 2
    if accel < 1:
        return None

    surge = _tv_surge(data, idx, 20)
    vol_score = min(max(surge or 0, 0), 2)

    flow_score = (f20_bps + i20_bps) / 80  # 합 160bps면 2점
    accel_score = min(accel, 3)
    price_score = min((p_now / p_avg - 1) * 10, 2)

    return flow_score * 0.35 + accel_score * 0.25 + price_score * 0.20 + vol_score * 0.20


def signal_accumulation_v1(data, idx):
    """집중매수 V1 — Pure Momentum (외인+기관 가속 매수)

    가설: 외인+기관 모두 양수 + 가속도 있는 매수 = 지속 모멘텀
    Components:
    - 20일 외인+기관 모두 양수 (지속 매수)
    - 5일 / 20일 daily ratio > 1 (가속도)
    - 양 투자자 동조 (alignment)
    """
    f = data.get("foreign", [])
    i = data.get("inst", [])
    if idx < 20 or idx >= len(f):
        return None

    f20 = safe_sum(f, idx - 20, idx)
    i20 = safe_sum(i, idx - 20, idx)
    f5 = safe_sum(f, idx - 5, idx)
    i5 = safe_sum(i, idx - 5, idx)
    if any(x is None for x in [f20, i20, f5, i5]):
        return None

    # 외인+기관 모두 매수 조건
    if f20 <= 0 or i20 <= 0:
        return None

    norm_f = rolling_normalize(f, idx, window=252)
    norm_i = rolling_normalize(i, idx, window=252)
    if norm_f is None or norm_i is None:
        return None

    # 매수 강도 (정규화)
    f_strength = f20 / (norm_f * 20)
    i_strength = i20 / (norm_i * 20)

    # 가속도 (5일 daily rate vs 20일 daily rate)
    f_accel = (f5 / 5) / (f20 / 20) if f20 > 0 else 0
    i_accel = (i5 / 5) / (i20 / 20) if i20 > 0 else 0
    accel = (f_accel + i_accel) / 2

    # 가속도가 음수 (5일 < 0) 거나 작으면 시그널 약함
    if accel < 1:  # 5일 daily가 20일 daily보다 작음 → 둔화
        return None

    return (f_strength + i_strength) * 0.5 + accel * 0.5


# ───────────────────────────────────────────────────────────
# Backtest Engine
# ───────────────────────────────────────────────────────────

def date_to_idx(data, date_str):
    """data["dates"] 배열에서 date_str의 인덱스 (없으면 None)"""
    try:
        return data["dates"].index(date_str)
    except ValueError:
        return None


def build_market_context(timeseries):
    """시장 전체 context 사전 계산.
    - kospi_index: {date: KOSPI 종가 추정 (대형주 시총 가중 평균 등)}
    - 우리는 KOSPI 종가가 timeseries에 없으니, 시장 전체 가격 가중평균으로 proxy
    - 간단한 proxy: 시총 상위 30개 평균 가격 변동률

    실제 KOSPI 종가가 시급하면 별도 백필 필요. 일단 proxy 사용.
    """
    # 모든 날짜 수집
    all_dates_set = set()
    for d in timeseries.values():
        all_dates_set.update(d.get("dates", []))
    all_dates = sorted(all_dates_set)

    # 각 날짜의 "시장" 종가 추정 = 그 날 시총 상위 종목들의 가격 평균
    # 단순화: 전체 종목 prices 평균 (모든 종목 동일 가중)
    # 더 정확: 종목별 첫날 시총 가중 → 시간 들어 일단 simple equal-weighted

    # date_str → list of valid prices
    date_to_prices = {d: [] for d in all_dates}
    for ticker, ts in timeseries.items():
        dates = ts.get("dates", [])
        prices = ts.get("prices", [])
        for i, d in enumerate(dates):
            if i < len(prices) and prices[i] and prices[i] > 0:
                date_to_prices[d].append(prices[i])

    # equal-weighted log-return index
    sorted_dates = all_dates
    market_index = {}
    prev_avg = None
    cum_idx = 100.0
    for d in sorted_dates:
        ps = date_to_prices[d]
        if not ps:
            market_index[d] = cum_idx
            continue
        cur_avg = sum(ps) / len(ps)
        if prev_avg is not None and prev_avg > 0:
            ret = cur_avg / prev_avg - 1
            cum_idx *= (1 + ret)
        market_index[d] = cum_idx
        prev_avg = cur_avg

    return {"market_index": market_index, "dates_sorted": sorted_dates}


def kospi_momentum_60d(market_ctx, date):
    """그 날짜 기준 60일 (대략 60 영업일) 시장 모멘텀"""
    dates_sorted = market_ctx["dates_sorted"]
    market_index = market_ctx["market_index"]
    try:
        idx = dates_sorted.index(date)
    except ValueError:
        return None
    if idx < 60:
        return None
    cur = market_index[date]
    past = market_index[dates_sorted[idx - 60]]
    if past is None or past <= 0:
        return None
    return cur / past - 1


def run_backtest(timeseries, signal_func, top_n=30, date_filter=None, use_context=False, market_ctx=None):
    """
    시그널 함수로 모든 ticker × 모든 date 백테스트

    timeseries: {ticker: data}
    signal_func: (data, idx) -> score | None
    top_n: 각 날짜에서 상위 N개만 시그널로 채택 (cross-sectional ranking)
    date_filter: (start_date, end_date) tuple, 둘 다 "YYYY-MM-DD" 또는 None

    Returns: list of dicts [{date, ticker, score, ret5, ret20, ...}]
    """
    # 가장 긴 timeseries 기준으로 날짜 범위 구함
    all_dates_seen = set()
    for d in timeseries.values():
        all_dates_seen.update(d.get("dates", []))
    all_dates = sorted(all_dates_seen)

    # date_filter 적용
    if date_filter:
        start, end = date_filter
        all_dates = [d for d in all_dates if start <= d <= end]

    # forward return 위한 여유 (마지막 20일 제외)
    eval_dates = all_dates[:-20] if len(all_dates) > 20 else []

    results = []

    # Context (regime filter용)
    ctx_for_date = {}
    if use_context and market_ctx:
        for d in eval_dates:
            mom = kospi_momentum_60d(market_ctx, d)
            ctx_for_date[d] = {"kospi_mom60": mom}

    for date in eval_dates:
        ctx = ctx_for_date.get(date) if use_context else None
        # 그 날의 모든 시그널 종목 점수 수집
        scores = {}
        for ticker, data in timeseries.items():
            idx = date_to_idx(data, date)
            if idx is None:
                continue
            if use_context:
                score = signal_func(data, idx, ctx)
            else:
                score = signal_func(data, idx)
            if score is None or score <= 0:
                continue
            scores[ticker] = (score, idx)

        if not scores:
            continue

        # 상위 N개
        sorted_signals = sorted(scores.items(), key=lambda x: -x[1][0])[:top_n]

        for ticker, (score, idx) in sorted_signals:
            data = timeseries[ticker]
            prices = data.get("prices", [])
            if idx >= len(prices):
                continue
            p_now = prices[idx]
            if p_now is None or p_now <= 0:
                continue

            row = {"date": date, "ticker": ticker, "score": score}
            for w in FORWARD_WINDOWS:
                future_idx = idx + w
                if future_idx < len(prices):
                    p_future = prices[future_idx]
                    if p_future and p_future > 0:
                        row[f"ret{w}"] = p_future / p_now - 1
                    else:
                        row[f"ret{w}"] = None
                else:
                    row[f"ret{w}"] = None

            results.append(row)

    return results


# ───────────────────────────────────────────────────────────
# Metrics
# ───────────────────────────────────────────────────────────

def compute_metrics(results, window=20, benchmark_avg=0.0):
    """results: backtest 결과 list
    window: forward 측정 기간 (5, 20 등)
    benchmark_avg: 해당 기간 시장 평균 수익률 (없으면 0)

    Returns: dict of metrics
    """
    key = f"ret{window}"
    valid = [r[key] for r in results if r.get(key) is not None]
    if not valid:
        return None

    n = len(valid)
    avg = statistics.mean(valid)
    median = statistics.median(valid)
    hit_rate = sum(1 for r in valid if r > 0) / n
    std = statistics.stdev(valid) if n > 1 else 0

    # TC 차감 (round-trip)
    avg_after_tc = avg - TC_ROUNDTRIP

    # Annualized Sharpe (rough — 250 trading days / window)
    sharpe = (avg / std) * ((250 / window) ** 0.5) if std > 0 else 0
    sharpe_after_tc = (avg_after_tc / std) * ((250 / window) ** 0.5) if std > 0 else 0

    # Excess over benchmark
    excess = avg - benchmark_avg

    # t-statistic (rough, assumes normal)
    t_stat = (avg / (std / (n ** 0.5))) if std > 0 else 0

    return {
        "n": n,
        "avg_return": avg,
        "median_return": median,
        "avg_after_tc": avg_after_tc,
        "hit_rate": hit_rate,
        "std": std,
        "sharpe": sharpe,
        "sharpe_after_tc": sharpe_after_tc,
        "excess_vs_bench": excess,
        "t_stat": t_stat,
    }


def regime_split_metrics(results, regimes, window=20):
    """국면별 metric 계산. results를 regime별로 나눠서."""
    out = {}
    for name, start, end in regimes:
        subset = [r for r in results if start <= r["date"] <= end]
        m = compute_metrics(subset, window=window)
        out[name] = m
    return out


def train_test_metrics(results, train_end_date, window=20):
    """Walk-forward train/test split"""
    train = [r for r in results if r["date"] <= train_end_date]
    test = [r for r in results if r["date"] > train_end_date]
    return {
        "train": compute_metrics(train, window=window),
        "test": compute_metrics(test, window=window),
    }


# ───────────────────────────────────────────────────────────
# Reporting
# ───────────────────────────────────────────────────────────

def format_pct(v):
    if v is None:
        return "  -  "
    return f"{v*100:+6.2f}%"


def print_metrics_table(label, metrics):
    if metrics is None:
        print(f"  {label}: NO DATA")
        return
    print(f"  {label}:")
    print(f"    N signals:       {metrics['n']:>8d}")
    print(f"    Avg return:      {format_pct(metrics['avg_return'])}")
    print(f"    Avg after TC:    {format_pct(metrics['avg_after_tc'])}")
    print(f"    Median return:   {format_pct(metrics['median_return'])}")
    print(f"    Hit rate:        {metrics['hit_rate']*100:5.1f}%")
    print(f"    Std:             {format_pct(metrics['std'])}")
    print(f"    Sharpe (ann):    {metrics['sharpe']:6.2f}")
    print(f"    Sharpe ann (TC): {metrics['sharpe_after_tc']:6.2f}")
    print(f"    t-stat:          {metrics['t_stat']:6.2f}")


# ───────────────────────────────────────────────────────────
# Main
# ───────────────────────────────────────────────────────────

SIGNAL_MAP = {
    "buy_reversal":  {"v1": signal_buy_reversal_v1,  "v2": signal_buy_reversal_v2,  "v3": signal_buy_reversal_v3,  "direction": "long"},
    "sell_reversal": {"v1": signal_sell_reversal_v1, "v2": signal_sell_reversal_v2, "v3": signal_sell_reversal_v3, "direction": "short"},
    "leader":        {"v1": signal_leader_v1,        "v2": signal_leader_v2,        "v3": signal_leader_v3,        "direction": "long"},
    "accumulation":  {"v1": signal_accumulation_v1,  "v2": signal_accumulation_v2,  "v3": signal_accumulation_v3,  "direction": "long"},
}


# ───────────────────────────────────────────────────────────
# Long-term Signals (60d holding) — backtest_longterm.py에서 검증된 전략 A & E
# ───────────────────────────────────────────────────────────


def _price_mom(prices, idx, n):
    if idx < n or idx >= len(prices):
        return None
    p_now = prices[idx]
    p_past = prices[idx - n]
    if not p_now or not p_past or p_now <= 0 or p_past <= 0:
        return None
    return p_now / p_past - 1


def _positive_days_ratio(arr, start, end):
    if start < 0 or end > len(arr) or end <= start:
        return None
    window = arr[start:end]
    if not window:
        return None
    return sum(1 for v in window if v > 0) / len(window)


def signal_nps_momentum(data, idx, ctx=None):
    """장기 A: NPS-Confirmed Momentum
    백테스트 (10년): t-stat 9.98, +4.99% TC adj / 60일 hold, walk-fwd Test +11%
    조건: 12-1 momentum + 60일 모멘텀 + 연기금 60일 bps + 외인기관 동조 + 거래량
    """
    f = data.get("foreign", [])
    inst = data.get("inst", [])
    pension = data.get("pension", [])
    p = data.get("prices", [])
    if idx < 252 or idx >= len(f) or idx >= len(p):
        return None

    mcap = _mcap_at(data, idx)
    if mcap is None or mcap < 50_000_000_000:
        return None

    mom_12 = _price_mom(p, idx - 20, 252 - 20)
    if mom_12 is None or mom_12 <= 0:
        return None
    mom_60 = _price_mom(p, idx, 60)
    if mom_60 is None or mom_60 <= 0:
        return None

    pen_60 = safe_sum(pension, idx - 60, idx)
    if pen_60 is None:
        return None
    pen_bps = _flow_bps(pen_60, mcap)
    if pen_bps is None or pen_bps < 5:
        return None

    f60 = safe_sum(f, idx - 60, idx)
    i60 = safe_sum(inst, idx - 60, idx)
    if f60 is None or i60 is None:
        return None
    fi_bps = _flow_bps(f60 + i60, mcap)
    if fi_bps is None or fi_bps < 0:
        return None

    surge = _tv_surge(data, idx, 20) or 0

    # Composite score (높을수록 좋음). 절대값이 아니라 상대 ranking에 사용
    return mom_12 * 0.25 + mom_60 * 0.20 + pen_bps / 100 * 0.30 + fi_bps / 100 * 0.15 + surge * 0.10


def signal_pension_divergence(data, idx, ctx=None):
    """장기 E: Pension vs Foreign Divergence (외국인 매도 + 연기금 매수)
    백테스트 (10년): t-stat 6.89, +1.68% TC adj / 60일 hold, walk-fwd Train+Test 양수
    Regime robust (2022 약세장 +1.54%)
    """
    f = data.get("foreign", [])
    pension = data.get("pension", [])
    p = data.get("prices", [])
    if idx < 60 or idx >= len(f) or idx >= len(p):
        return None

    mcap = _mcap_at(data, idx)
    if mcap is None or mcap < 50_000_000_000:
        return None

    pen_60 = safe_sum(pension, idx - 60, idx)
    if pen_60 is None or pen_60 <= 0:
        return None
    pen_bps = _flow_bps(pen_60, mcap)
    if pen_bps is None or pen_bps < 5:
        return None

    f60 = safe_sum(f, idx - 60, idx)
    if f60 is None or f60 >= 0:
        return None
    f_bps = _flow_bps(f60, mcap)
    if f_bps is None or f_bps > -3:
        return None

    mom_60 = _price_mom(p, idx, 60)
    if mom_60 is None or mom_60 < -0.15 or mom_60 > 0.10:
        return None

    pen_pos = _positive_days_ratio(pension, idx - 60, idx)
    if pen_pos is None or pen_pos < 0.40:
        return None

    # Composite (분리 정규화는 어렵지만 단순 합산으로 ranking)
    return pen_bps / 100 * 0.35 + (-f_bps) / 100 * 0.30 + pen_pos * 0.20 + (-abs(mom_60)) * 0.15


# Long-term signal map (별도)
LONGTERM_SIGNAL_MAP = {
    "nps_momentum": signal_nps_momentum,
    "divergence": signal_pension_divergence,
}


def run_one_signal(timeseries, name, candidate, top_n, market_ctx=None):
    """단일 시그널 1개 후보 백테스트 + 출력"""
    entry = SIGNAL_MAP[name]
    signal_func = entry[candidate]
    direction = entry["direction"]
    expected_sign = "양수(매수 시그널)" if direction == "long" else "음수(매도 시그널, short)"
    use_ctx = candidate in ("v2", "v3")  # V2부터 context 사용

    print(f"\n{'='*70}")
    print(f"  [{name}] / {candidate} | top-{top_n} | 기대: {expected_sign}{' | ctx=ON' if use_ctx else ''}")
    print(f"{'='*70}")

    t0 = time.time()
    results = run_backtest(timeseries, signal_func, top_n=top_n,
                           use_context=use_ctx, market_ctx=market_ctx)
    print(f"  Backtest events: {len(results)} ({time.time() - t0:.1f}s)")

    if not results:
        print("  NO RESULTS")
        return

    # 5일 forward
    print("\n  --- 전체 10년 (5일 forward) ---")
    m5 = compute_metrics(results, window=5)
    print_metrics_table("Overall 5d", m5)

    # 20일 forward
    print("\n  --- 전체 10년 (20일 forward) ---")
    m = compute_metrics(results, window=20)
    print_metrics_table("Overall 20d", m)
    print(f"\n    ※ 매수 시그널이면 avg_return > 0 + hit_rate > 50% 기대")
    print(f"       매도 시그널이면 avg_return < 0 + hit_rate < 50% 기대")

    # Walk-forward
    print(f"\n  --- Walk-forward (Train ≤ {TRAIN_END_DATE}) ---")
    tt = train_test_metrics(results, TRAIN_END_DATE, window=20)
    if tt["train"] and tt["test"]:
        print(f"    Train: avg={format_pct(tt['train']['avg_return'])} "
              f"hit={tt['train']['hit_rate']*100:5.1f}% sharpe={tt['train']['sharpe']:5.2f}")
        print(f"    Test : avg={format_pct(tt['test']['avg_return'])} "
              f"hit={tt['test']['hit_rate']*100:5.1f}% sharpe={tt['test']['sharpe']:5.2f}")

    # Regime split
    print(f"\n  --- Regime Split ---")
    rs = regime_split_metrics(results, REGIMES, window=20)
    for rname, rm in rs.items():
        if rm:
            print(f"    [{rname:10s}] N={rm['n']:>6d}  "
                  f"avg={format_pct(rm['avg_return'])}  "
                  f"hit={rm['hit_rate']*100:5.1f}%  "
                  f"sharpe={rm['sharpe']:5.2f}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--signal", type=str, default="all", help="시그널 이름 (all/buy_reversal/...)")
    parser.add_argument("--candidate", type=str, default="v1", help="후보 (v1/v2/...)")
    parser.add_argument("--top-n", type=int, default=30, help="일별 상위 N개")
    args = parser.parse_args()

    timeseries = load_all_timeseries()

    # V2부터는 market context 필요 (regime filter)
    market_ctx = None
    if args.candidate in ("v2", "v3") or args.candidate == "all":
        print("Building market context...")
        t0 = time.time()
        market_ctx = build_market_context(timeseries)
        print(f"  market index dates: {len(market_ctx['dates_sorted'])} ({time.time() - t0:.1f}s)")

    if args.signal == "all":
        for name in SIGNAL_MAP.keys():
            if args.candidate in SIGNAL_MAP[name]:
                run_one_signal(timeseries, name, args.candidate, args.top_n, market_ctx)
    else:
        if args.signal not in SIGNAL_MAP or args.candidate not in SIGNAL_MAP[args.signal]:
            print(f"Unknown signal/candidate: {args.signal}/{args.candidate}")
            return
        run_one_signal(timeseries, args.signal, args.candidate, args.top_n, market_ctx)


if __name__ == "__main__":
    main()
