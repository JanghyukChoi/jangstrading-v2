"""
V3 시그널 계산기 (라이브)

입력: public/data/timeseries/*.json (종목별 시계열, 시총·거래량 포함)
출력: public/data/signals.json — 4개 V3 시그널 top-15 ticker 리스트

실행: python scripts/build_v3_signals.py

전제: build_timeseries.py가 augment된 snapshots로부터 먼저 실행되어 있어야 함.
      timeseries 파일에 market_cap, trade_value 필드 있어야 V3 작동.
"""

import json
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TS_DIR = BASE_DIR / "public" / "data" / "timeseries"
SNAP_DIR = BASE_DIR / "public" / "data" / "snapshots"
KOSPI_HISTORY_PATH = BASE_DIR / "public" / "data" / "kospi-history.json"
OUT_PATH = BASE_DIR / "public" / "data" / "signals.json"

# backtest_signals.py에서 V3 시그널 함수 + helper 재사용
sys.path.insert(0, str(BASE_DIR / "scripts"))
from backtest_signals import (  # noqa: E402
    MAX_LOOKBACK,
    spans_break,
    signal_buy_reversal_v3,
    signal_sell_reversal_v3,
    signal_leader_v3,
    signal_accumulation_v3,
    ai_screener_factors,
    composite_ai_screener_pct,
)
from price_adjust import discontinuities  # noqa: E402


def build_kospi_context():
    """KOSPI 종가 시계열 로드 (fetch_kospi_history.py가 만든 cache).
    fallback: snapshot.market.kospi 사용 (cache 없을 때).
    """
    # 우선 kospi-history.json
    if KOSPI_HISTORY_PATH.exists():
        try:
            mi = json.load(open(KOSPI_HISTORY_PATH, "r", encoding="utf-8"))
            mi = {d: float(v) for d, v in mi.items() if v}
            return {"market_index": mi, "dates_sorted": sorted(mi.keys())}
        except Exception:
            pass
    # Fallback: snapshots
    market_index = {}
    for f in sorted(SNAP_DIR.glob("*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fp:
                d = json.load(fp)
        except Exception:
            continue
        kospi = (d.get("market") or {}).get("kospi")
        if kospi and kospi > 0:
            market_index[d.get("date", f.stem)] = kospi
    return {
        "market_index": market_index,
        "dates_sorted": sorted(market_index.keys()),
    }


def kospi_momentum_60d(ctx, date):
    """60 영업일 전 대비 KOSPI 모멘텀"""
    ds = ctx["dates_sorted"]
    mi = ctx["market_index"]
    try:
        idx = ds.index(date)
    except ValueError:
        return None
    if idx < 60:
        return None
    cur = mi[date]
    past = mi[ds[idx - 60]]
    if not past or past <= 0:
        return None
    return cur / past - 1

TOP_N = 15
LONGTERM_TOP_N = 5  # 백테스트 (top-5 overlap)와 정합

# 단기 4종(매수전환·매도전환·주도주·단기수급상위)은 내렸다.
#
# 10.3년(2016-02~2026-05, 3,234종목, 상장폐지 포함) 재검정에서 같은 날 같은
# 시총 하한 모집단의 평균을 뺀 초과수익이 사실상 없었고, 기간을 나누면 부호가
# 뒤집혔다. v1 은 train(~2022)에서만, v3 는 test(2023~)에서만 작동한다 —
# v1->v2->v3 로 다듬는 과정 자체가 다중검정이었고 각 버전은 자기가 맞춰진
# 구간에서만 산다. 어느 버전도 두 구간을 모두 통과하지 못했다.
# 수치는 scripts/backtest_signals.py 참고.
#
# 함수 정의는 backtest_signals.py 에 그대로 있다. 재검정하거나 되살릴 때
# 여기에 다시 등록하면 된다.
SIGNAL_FNS = {}

# 장기 시그널: factor dict 반환 함수 + cross-section 백분위 composite
# (백테스트 backtest_longterm.py의 score_strategy_a + composite_a와 정합)
# 장기수급상위(ai_screener)도 내렸다.
#
# 단기 4종과 같은 기계로 재보니(backtest_longterm_check.py) 근거가 없다.
# 60일 보유 11,000 거래를 독립 관측으로 세면 t=11 이 나오지만, 같은 날 여러
# 종목을 한 관측으로 묶고 중첩 보유의 자기상관을 Newey-West 로 보정하면:
#
#   보유    초과      t(단순)  t(날짜군집+NW)  승률    중앙값
#    5일   +0.35%     4.12       1.96        46.6%  -0.56%
#   20일   +1.64%     9.63       2.52        47.5%  -1.02%
#   60일   +3.64%    11.02       1.77        44.4%  -3.50%
#
#   train(~2022) 7년:  5일 t=0.16 / 20일 t=0.65 / 60일 t=0.59
#
# train 구간에 신호가 없고, 중앙값이 전부 음수다(60일 보유 시 절반 이상이
# -3.5% 보다 나쁘다). 평균은 소수의 큰 승자가 끌어올린 것이다.
#
# 이 신호는 연기금 60일 순매수 >= 5bp 를 필수 조건으로 걸고 가중치의 30% 를
# 연기금에 준다. 사내 원장의 152팩터 장기 검정에서 연기금은 예측력이 있으나
# **방향이 반대**였다(t(h=20) -4.49, 단조성 rho -0.78).
#
# 함수 정의는 backtest_signals.py 에 그대로 있다.
LONGTERM_FACTOR_FNS = {}
LONGTERM_COMPOSITE_FNS = {}


def load_timeseries():
    files = [f for f in TS_DIR.glob("*.json") if f.stem != "_index"]
    data = {}
    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fp:
                d = json.load(fp)
            ticker = d.get("ticker") or f.stem
            # 액면분할은 build_timeseries 가 보정했다. 보정 불가능한 단절
            # (무상증자 권리락 등)의 위치만 기억해 둔다 — 그 구간을 지나는
            # 모멘텀은 -62% 같은 값이 나와 시그널이 통째로 틀린다.
            d["_disc"] = discontinuities(d.get("prices") or [], d.get("market_cap") or [])
            data[ticker] = d
        except Exception:
            continue
    ndisc = sum(1 for d in data.values() if d["_disc"])
    if ndisc:
        print(f"  가격 단절 있는 종목 {ndisc}개 — 해당 구간은 시그널에서 제외")
    return data


def main():
    t0 = time.time()
    print("=" * 60)
    print("V3 시그널 빌드 시작")
    print("=" * 60)

    print(f"  timeseries 로드 중... ({TS_DIR})")
    ts = load_timeseries()
    if not ts:
        print("[ERROR] timeseries 없음. build_timeseries.py 먼저 실행 필요.")
        return
    print(f"  종목: {len(ts):,}개")

    # 최신 영업일 찾기 (모든 timeseries에 공통으로 있는 마지막 날짜)
    all_dates = set()
    for d in ts.values():
        for dt in d.get("dates", []):
            all_dates.add(dt)
    if not all_dates:
        print("[ERROR] 영업일 데이터 없음")
        return
    latest_date = sorted(all_dates)[-1]
    print(f"  대상 영업일: {latest_date}")

    # KOSPI context (regime filter용 — 실제 KOSPI index 종가 시계열)
    print("  시장 context 계산 중...")
    kospi_ctx = build_kospi_context()
    print(f"  KOSPI index 일수: {len(kospi_ctx['dates_sorted'])}")
    mom = kospi_momentum_60d(kospi_ctx, latest_date)
    ctx = {"kospi_mom60": mom}
    if mom is not None:
        print(f"  KOSPI 60일 모멘텀: {mom*100:+.2f}%")
    else:
        print(f"  KOSPI 60일 모멘텀: 데이터 부족")

    # 단기(V3) 시그널: 각각 top-15
    print()
    print("  -- 단기 시그널 (V3) --")
    results = {}
    for name, fn in SIGNAL_FNS.items():
        scored = []
        for ticker, data in ts.items():
            dates = data.get("dates", [])
            try:
                idx = dates.index(latest_date)
            except ValueError:
                continue
            if spans_break(data, idx - MAX_LOOKBACK, idx):
                continue
            score = fn(data, idx, ctx)
            if score is not None and score > 0:
                scored.append((ticker, score))
        scored.sort(key=lambda x: -x[1])
        top = scored[:TOP_N]
        results[name] = [t for t, _ in top]
        print(f"  [{name:14s}] raw {len(scored):4d} -> top-{TOP_N}: {len(top)}개")

    # 장기(60일 보유) 시그널: cross-section 백분위 ranking → top-N
    print()
    print("  -- 장기 시그널 (60일 보유, 백분위 ranking) --")
    longterm = {}
    for name, factor_fn in LONGTERM_FACTOR_FNS.items():
        composite_fn = LONGTERM_COMPOSITE_FNS[name]
        # 1) 조건 통과 종목들의 raw factors 수집
        candidates = []  # [(ticker, factors_dict), ...]
        for ticker, data in ts.items():
            dates = data.get("dates", [])
            try:
                idx = dates.index(latest_date)
            except ValueError:
                continue
            if spans_break(data, idx - MAX_LOOKBACK, idx):
                continue
            f = factor_fn(data, idx, ctx)
            if f is not None:
                candidates.append((ticker, f))
        # 2) cross-section 백분위 합성 점수
        all_factors = [f for _, f in candidates]
        scored = [(t, composite_fn(f, all_factors)) for t, f in candidates]
        scored.sort(key=lambda x: -x[1])
        top = scored[:LONGTERM_TOP_N]
        longterm[name] = [t for t, _ in top]
        print(f"  [{name:14s}] candidates {len(candidates):4d} -> top-{LONGTERM_TOP_N}: {len(top)}개")

    output = {
        "date": latest_date,
        "version": "v3",
        "top_n": TOP_N,
        "signals": results,
        "longterm": longterm,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = OUT_PATH.stat().st_size / 1024
    print()
    print(f"OK {OUT_PATH.name} ({size_kb:.1f} KB) - {time.time() - t0:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
