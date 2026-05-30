"""
일일 스냅샷 저장 스크립트
수급 신호 발생 종목 + 전 종목 종가 + 종목별 일별 순매수 + Breadth + 시장 지수

저장: public/data/snapshots/YYYY-MM-DD.json
용량: 하루 ~110KB, 1년 ~25MB, 2년 ~50MB
Retention: 최대 500 영업일 (~2년) 유지, 초과 시 가장 오래된 파일 자동 삭제

실행: python scripts/save_snapshot.py
"""

import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "public" / "data"
SNAP_DIR = DATA_DIR / "snapshots"

# 최대 보관 영업일 수 (약 2년)
MAX_SNAPSHOTS = 500

# YYYY-MM-DD.json 형식만 retention 대상
SNAPSHOT_FILENAME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def main():
    rankings_path = DATA_DIR / "stock-rankings.json"
    with open(rankings_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    stocks = data["data"]
    date = data["date"]

    print(f"📸 스냅샷 저장 시작 ({date})")

    # 1. 시그널 판정은 V3 (build_v3_signals.py)에서 timeseries 기반으로 계산.
    #    snapshot 자체에는 empty placeholder만 저장. 실제 시그널은 public/data/signals.json.
    signals = {"buy_reversal": [], "sell_reversal": [], "leader": [], "accumulation": []}

    # 2. 전 종목 종가
    prices = {}
    for s in stocks:
        t = s.get("ticker", "")
        if t and s.get("avg_cost"):
            prices[t] = s["avg_cost"].get("price", 0)

    # 종가가 avg_cost에 없는 경우 대비
    if len(prices) < 100:
        # price_change에서 역산 불가하므로 빈 dict 유지
        pass

    # 2.5. 종목별 일별 순매수 금액 (외국인/기관/연기금, 단위: 백만원)
    # → 누적 시계열 라인 차트의 핵심 데이터. 매일 누적되면 30일 차트 가능.
    foreign_1d = {}
    inst_1d = {}
    pension_1d = {}
    for s in stocks:
        t = s.get("ticker", "")
        if not t:
            continue
        f_val = s.get("foreign", {}).get("1d", 0)
        i_val = s.get("institution", {}).get("1d", 0)
        p_val = (s.get("pension") or {}).get("1d", 0)
        # 0이 아닌 값만 저장해서 파일 크기 절약
        if f_val:
            foreign_1d[t] = round(f_val, 1)
        if i_val:
            inst_1d[t] = round(i_val, 1)
        if p_val:
            pension_1d[t] = round(p_val, 1)

    # 3. 수급 Breadth (1일 기준)
    foreign_buy = sum(1 for s in stocks if s["foreign"].get("1d", 0) > 0)
    foreign_sell = sum(1 for s in stocks if s["foreign"].get("1d", 0) < 0)
    inst_buy = sum(1 for s in stocks if s["institution"].get("1d", 0) > 0)
    inst_sell = sum(1 for s in stocks if s["institution"].get("1d", 0) < 0)

    breadth = {
        "foreign_buy": foreign_buy,
        "foreign_sell": foreign_sell,
        "inst_buy": inst_buy,
        "inst_sell": inst_sell,
    }

    # 4. 시장 지수
    market = {}
    try:
        with open(DATA_DIR / "market-overview.json", "r", encoding="utf-8") as f:
            mo = json.load(f)["data"]
        for m in ["KOSPI", "KOSDAQ"]:
            idx = mo.get(m, {}).get("index")
            if isinstance(idx, dict):
                market[m.lower()] = idx.get("value", 0)
            elif isinstance(idx, (int, float)):
                market[m.lower()] = idx
    except Exception:
        pass

    # 5. 저장
    snapshot = {
        "date": date,
        "signals": signals,
        "prices": prices,
        "foreign_1d": foreign_1d,
        "inst_1d": inst_1d,
        "pension_1d": pension_1d,
        "breadth": breadth,
        "market": market,
    }

    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    snap_path = SNAP_DIR / f"{date}.json"
    with open(snap_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False)

    size_kb = snap_path.stat().st_size / 1024
    print(f"  📊 신호: V3 시그널은 build_v3_signals.py에서 별도 계산 (signals.json)")
    print(f"  💰 종가: {len(prices)}종목")
    print(f"  📈 일별 수급: 외국인 {len(foreign_1d)} / 기관 {len(inst_1d)} / 연기금 {len(pension_1d)} 종목")
    print(f"  📈 Breadth: 외국인 +{breadth['foreign_buy']}/-{breadth['foreign_sell']} | 기관 +{breadth['inst_buy']}/-{breadth['inst_sell']}")
    print(f"  ✅ {snap_path} 저장 완료 ({size_kb:.1f} KB)")

    # 6. Retention: 최대 MAX_SNAPSHOTS 영업일만 유지, 오래된 것 삭제
    snap_files = sorted(
        (f for f in SNAP_DIR.glob("*.json") if SNAPSHOT_FILENAME_RE.match(f.stem)),
        key=lambda f: f.stem,
        reverse=True,  # 최신부터
    )
    to_delete = snap_files[MAX_SNAPSHOTS:]
    if to_delete:
        for old in to_delete:
            old.unlink()
        oldest_kept = snap_files[MAX_SNAPSHOTS - 1].stem if len(snap_files) > MAX_SNAPSHOTS else "-"
        print(f"  🗑️  retention: {len(to_delete)}개 삭제 (오래된 순), 보관 시작일 {oldest_kept}")


if __name__ == "__main__":
    main()
