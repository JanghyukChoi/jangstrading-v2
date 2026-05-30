"""
시장 신호 대시보드 빌드

목적: 홈 페이지의 "시장 신호" 섹션에 표시할 액션 가능한 지표 컴파일.

입력:
- public/data/snapshots/*.json (일별 스냅샷)
- public/data/timeseries/*.json (종목별 시계열)

출력:
- public/data/market-signals.json

산출 지표:
- 추세: 외국인/기관 시장 전체 N거래일 연속 매수/매도 일수 + 누적 금액
- 활기: 52주 신고가/신저가 종목 수, breadth (매수/매도 종목 수)
- 시그널: 매수전환/매도전환/집중매수/괴리 신호 종목 수
- Verdict: 한 줄 결론

실행: python scripts/build_market_signals.py
"""

import json
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "public" / "data"
SNAP_DIR = DATA_DIR / "snapshots"
TS_DIR = DATA_DIR / "timeseries"
OUT_PATH = DATA_DIR / "market-signals.json"


def calc_streak(daily_values):
    """가장 최근부터 거꾸로 가며 부호 동일한 연속 일수와 누적 금액 계산.
    반환: (streak_days, streak_amount). 매도 streak이면 둘 다 음수."""
    if not daily_values:
        return 0, 0
    last_sign = 1 if daily_values[-1] > 0 else (-1 if daily_values[-1] < 0 else 0)
    if last_sign == 0:
        return 0, 0
    streak_days = 0
    streak_amount = 0
    for v in reversed(daily_values):
        cur_sign = 1 if v > 0 else (-1 if v < 0 else 0)
        if cur_sign == last_sign:
            streak_days += 1
            streak_amount += v
        else:
            break
    return streak_days * last_sign, streak_amount


def calc_market_trend(snaps, ticker_to_market, target_market):
    """특정 시장(KOSPI/KOSDAQ)의 일별 외인·기관 합계 → streak 계산"""
    foreign_daily = []
    inst_daily = []
    for sp in snaps:
        try:
            with open(sp, "r", encoding="utf-8") as f:
                snap = json.load(f)
        except Exception:
            continue
        f_dict = snap.get("foreign_1d") or {}
        i_dict = snap.get("inst_1d") or {}
        if not f_dict and not i_dict:
            continue
        f_sum = sum(v for t, v in f_dict.items() if ticker_to_market.get(t) == target_market)
        i_sum = sum(v for t, v in i_dict.items() if ticker_to_market.get(t) == target_market)
        foreign_daily.append(f_sum)
        inst_daily.append(i_sum)
    f_streak_days, f_streak_amount = calc_streak(foreign_daily)
    i_streak_days, i_streak_amount = calc_streak(inst_daily)
    return {
        "foreign_streak_days": f_streak_days,
        "foreign_streak_amount": round(f_streak_amount, 1),
        "inst_streak_days": i_streak_days,
        "inst_streak_amount": round(i_streak_amount, 1),
    }


def generate_verdict(kospi, kosdaq, signals, high, low):
    """KOSPI·KOSDAQ 시장별 trend + 시그널 종합해 한 줄 결론 생성"""
    kf = kospi["foreign_streak_days"]
    ki = kospi["inst_streak_days"]
    qf = kosdaq["foreign_streak_days"]
    qi = kosdaq["inst_streak_days"]

    # 1) KOSPI/KOSDAQ에서 외인이 반대 방향 = 자금 이동 시그널 (가장 의미 큰 패턴)
    if kf < -2 and qf > 2:
        return f"외인 KOSPI 매도 {abs(kf)}일 vs KOSDAQ 매수 {qf}일. 대형주 → 중소형주 자금 이동."
    if kf > 2 and qf < -2:
        return f"외인 KOSPI 매수 {kf}일 vs KOSDAQ 매도 {abs(qf)}일. 중소형주 → 대형주 자금 회귀."

    # 2) KOSPI 외인·기관 동시 강세/약세 (시장 방향 명확)
    if kf > 2 and ki > 2:
        return f"외인·기관 KOSPI 동시 매수 {min(kf, ki)}일, 신고가 {high}개. 추세 추종 매매 유효."
    if kf < -2 and ki < -2:
        return f"외인·기관 KOSPI 동시 매도 {min(abs(kf), abs(ki))}일, 신저가 {low}개. 방어적 포지션 권장."

    # 3) KOSPI 의견 분열
    if kf * ki < 0:
        f_dir = "매수" if kf > 0 else "매도"
        i_dir = "매수" if ki > 0 else "매도"
        return f"KOSPI에서 외인 {abs(kf)}일 {f_dir} vs 기관 {abs(ki)}일 {i_dir}, 의견 분열. 종목 선별 매매 권장."

    # 4) 시그널 기반
    if signals["buy_reversal"] > signals["sell_reversal"]:
        return f"매수전환 신호 {signals['buy_reversal']}개 (매도전환 {signals['sell_reversal']}개). 반등 후보 종목 모니터링."
    if signals["sell_reversal"] > signals["buy_reversal"]:
        return f"매도전환 신호 {signals['sell_reversal']}개 (매수전환 {signals['buy_reversal']}개). 추세 약화, 관망 권장."
    return "추세 약함 · 시그널 중립. 종목 선별 매매 권장."


def main():
    t0 = time.time()
    print("=" * 60)
    print("시장 신호 빌드 시작")
    print("=" * 60)

    # 1. 스냅샷 수집
    snap_files = sorted(SNAP_DIR.glob("*.json"))
    if not snap_files:
        print("[ERROR] 스냅샷 파일 없음")
        return

    # 최근 30일치만 streak 계산용 (충분)
    recent_snaps = snap_files[-30:]
    print(f"  스냅샷: {len(snap_files)}개 (streak 계산용 최근 {len(recent_snaps)}일)")

    # ticker → market 매핑 (stock-rankings.json)
    try:
        with open(DATA_DIR / "stock-rankings.json", "r", encoding="utf-8") as f:
            rankings = json.load(f)
        ticker_to_market = {
            s.get("ticker"): s.get("market", "")
            for s in rankings.get("data", [])
            if s.get("ticker")
        }
        print(f"  종목 매핑: {len(ticker_to_market)}개")
    except Exception as e:
        print(f"  [WARN] stock-rankings.json 로드 실패: {e}")
        ticker_to_market = {}

    # KOSPI / KOSDAQ 시장별 trend 계산
    kospi_trend = calc_market_trend(recent_snaps, ticker_to_market, "KOSPI")
    kosdaq_trend = calc_market_trend(recent_snaps, ticker_to_market, "KOSDAQ")
    print(
        f"  KOSPI  추세: 외인 {kospi_trend['foreign_streak_days']:+d}일 / "
        f"기관 {kospi_trend['inst_streak_days']:+d}일"
    )
    print(
        f"  KOSDAQ 추세: 외인 {kosdaq_trend['foreign_streak_days']:+d}일 / "
        f"기관 {kosdaq_trend['inst_streak_days']:+d}일"
    )

    # 2. 최근 스냅샷에서 breadth 추출
    with open(snap_files[-1], "r", encoding="utf-8") as f:
        latest_snap = json.load(f)
    breadth = latest_snap.get("breadth") or {}
    latest_date = latest_snap.get("date", "")

    # V3 시그널은 별도 파일 (build_v3_signals.py가 만듦)
    signals_path = DATA_DIR / "signals.json"
    try:
        with open(signals_path, "r", encoding="utf-8") as f:
            v3 = json.load(f)
        v3_signals = v3.get("signals") or {}
    except Exception:
        v3_signals = {}

    signal_counts = {
        "buy_reversal": len(v3_signals.get("buy_reversal", [])),
        "sell_reversal": len(v3_signals.get("sell_reversal", [])),
        "leader": len(v3_signals.get("leader", [])),
        "accumulation": len(v3_signals.get("accumulation", [])),
    }
    print(
        f"  시그널 (V3): 매수전환 {signal_counts['buy_reversal']} / "
        f"매도전환 {signal_counts['sell_reversal']} / "
        f"주도주 {signal_counts['leader']} / "
        f"집중매수 {signal_counts['accumulation']}"
    )

    # 3. 52주 신고가/신저가 계산 (timeseries 기준)
    ts_files = [f for f in TS_DIR.glob("*.json") if f.stem != "_index"]
    high_52w = 0
    low_52w = 0
    valid_count = 0
    for tf in ts_files:
        try:
            with open(tf, "r", encoding="utf-8") as f:
                ts = json.load(f)
        except Exception:
            continue
        prices = ts.get("prices") or []
        # 0이 아닌 값만 유효
        valid_prices = [p for p in prices if p > 0]
        if len(valid_prices) < 60:  # 최소 3개월 데이터
            continue
        valid_count += 1
        latest_price = valid_prices[-1]
        if latest_price == max(valid_prices):
            high_52w += 1
        if latest_price == min(valid_prices):
            low_52w += 1
    print(f"  활기: 신고가 {high_52w} / 신저가 {low_52w} (검사 종목 {valid_count})")

    # 4. Verdict (KOSPI·KOSDAQ 종합)
    verdict = generate_verdict(kospi_trend, kosdaq_trend, signal_counts, high_52w, low_52w)
    print(f"  Verdict: {verdict}")

    # 5. 출력
    output = {
        "date": latest_date,
        "trend": {
            "kospi": kospi_trend,
            "kosdaq": kosdaq_trend,
        },
        "activity": {
            "high_52w": high_52w,
            "low_52w": low_52w,
            "foreign_buy_breadth": breadth.get("foreign_buy", 0),
            "foreign_sell_breadth": breadth.get("foreign_sell", 0),
            "inst_buy_breadth": breadth.get("inst_buy", 0),
            "inst_sell_breadth": breadth.get("inst_sell", 0),
        },
        "signals": signal_counts,
        "verdict": verdict,
    }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = OUT_PATH.stat().st_size / 1024
    print()
    print(f"✅ {OUT_PATH.name} ({size_kb:.1f} KB) — {time.time() - t0:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
