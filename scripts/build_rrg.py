"""
build_rrg.py  ─  섹터 수급 RRG 좌표 생성
Usage: python scripts/build_rrg.py
Output: public/data/rrg-data.json
"""

import json, os, glob
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SNAP_DIR = BASE / "public" / "data" / "snapshots"
SECTOR_MAP = BASE / "public" / "data" / "sector-map.json"
STOCK_RANKINGS = BASE / "public" / "data" / "stock-rankings.json"
OUTPUT = BASE / "public" / "data" / "rrg-data.json"

# ── 기간별 설정 ──────────────────────────────────
# window: X축 계산 윈도우 (거래일)
# sub: Y축 가속도 계산용 최근 구간 (거래일)
# step: 궤적 포인트 간격 (거래일)
# points: 궤적 포인트 수
CONFIGS = {
    "1d": {"window": 1,   "sub": 1,  "step": 1,  "points": 5},
    "1w": {"window": 5,   "sub": 1,  "step": 5,  "points": 4},
    "1m": {"window": 20,  "sub": 5,  "step": 5,  "points": 4},
    "3m": {"window": 60,  "sub": 20, "step": 5,  "points": 5},
    "6m": {"window": 120, "sub": 60, "step": 10, "points": 4},
}


def main():
    # 1. 섹터맵 & 시총 로드
    with open(SECTOR_MAP) as f:
        sector_map = json.load(f)
    with open(STOCK_RANKINGS) as f:
        sr = json.load(f)

    mcap_map = {}
    for s in sr["data"]:
        t = s.get("ticker", "")
        if t and s.get("market_cap"):
            mcap_map[t] = s["market_cap"]

    # stock-rankings에 저장된 KRX 공식 기간 누적값(테이블이 쓰는 값).
    # RRG 좌표·금액을 이 값에 캘리브레이션해서 테이블과 정합을 맞춘다.
    # (일별 스냅샷 합산은 외국인·기관은 ≈일치하나 연기금은 KRX 정정 탓에 크게 어긋남)
    def stored_dict(field):
        return {s["ticker"]: (s.get(field) or {})
                for s in sr["data"] if s.get("ticker")}

    INVESTOR_STORED = {
        "combined": stored_dict("combined"),
        "foreign": stored_dict("foreign"),
        "institution": stored_dict("institution"),
        "pension": stored_dict("pension"),
    }

    # 2. 전체 스냅샷 로드 → 투자자별 일별 종목 수급
    #    날짜 인덱스(idx)에 직접 값을 넣어 정렬한다. (append+pad 방식은
    #    중간에 처음 등장하는 신규 상장 종목의 값이 엉뚱한 날짜로 밀리는 버그가 있음)
    snap_files = sorted(glob.glob(str(SNAP_DIR / "*.json")))
    print(f"Loading {len(snap_files)} snapshots...")

    N = len(snap_files)
    foreign_flows = defaultdict(lambda: [0.0] * N)   # ticker -> [날짜별 외국인]
    inst_flows = defaultdict(lambda: [0.0] * N)      # ticker -> [날짜별 기관]
    pension_flows = defaultdict(lambda: [0.0] * N)   # ticker -> [날짜별 연기금]
    dates = []

    for idx, sf in enumerate(snap_files):
        with open(sf) as f:
            snap = json.load(f)
        dates.append(snap.get("date", os.path.basename(sf).replace(".json", "")))
        foreign_1d = snap.get("foreign_1d", {})
        inst_1d = snap.get("inst_1d", {})
        pension_1d = snap.get("pension_1d", {})

        for ticker, v in foreign_1d.items():
            foreign_flows[ticker][idx] = v or 0
        for ticker, v in inst_1d.items():
            inst_flows[ticker][idx] = v or 0
        for ticker, v in pension_1d.items():
            pension_flows[ticker][idx] = v or 0

    print(f"Date range: {dates[0]} ~ {dates[-1]} ({N} days)")

    # combined(외국인+기관) = foreign + inst (날짜별 합산)
    combined_flows = {}
    for ticker in set(foreign_flows) | set(inst_flows):
        ff = foreign_flows.get(ticker, [0.0] * N)
        ii = inst_flows.get(ticker, [0.0] * N)
        combined_flows[ticker] = [ff[i] + ii[i] for i in range(N)]

    # 투자자 키 → 종목별 일별 수급 시계열 (페이지 Investor 타입과 동일한 키 사용)
    INVESTOR_FLOWS = {
        "combined": combined_flows,
        "foreign": foreign_flows,
        "institution": inst_flows,
        "pension": pension_flows,
    }

    # 3. (투자자 × 분류레벨)별 RRG 좌표 계산
    #    level_key: sector_map 값에서 그룹 키 ("large" 또는 "mid")
    #    각 그룹의 색상(l)은 항상 대분류(large)로 매핑 → 컴포넌트 COLORS와 일치
    def build_level(level_key, daily_flows, stored_period):
        groups = set()
        for v in sector_map.values():
            g = v.get(level_key)
            if g and g != "기타":
                groups.add(g)

        grp_flows = {g: [0.0] * N for g in groups}
        grp_mcap = {g: 0 for g in groups}
        grp_large = {}
        # 그룹×기간별 KRX 공식 누적값 (테이블 정합용)
        grp_canon = {g: {p: 0.0 for p in CONFIGS} for g in groups}

        for ticker, sm in sector_map.items():
            g = sm.get(level_key, "기타")
            if g not in groups:
                continue
            grp_large[g] = sm.get("large", "기타")
            grp_mcap[g] += mcap_map.get(ticker, 0)
            sp = stored_period.get(ticker, {})
            for p in CONFIGS:
                grp_canon[g][p] += sp.get(p, 0) or 0
            flows = daily_flows.get(ticker, [])
            for i in range(min(len(flows), N)):
                grp_flows[g][i] += flows[i]

        level_result = {}
        for period, cfg in CONFIGS.items():
            w = cfg["window"]
            sub = cfg["sub"]
            step = cfg["step"]
            npts = cfg["points"]

            period_data = []
            for g in sorted(groups):
                mc = grp_mcap.get(g, 0)
                if mc <= 0:
                    continue
                flows = grp_flows[g]
                large = grp_large.get(g, "기타")

                # 캘리브레이션(평행이동): 일별로 측정한 '움직임(궤적 모양)'은 유지하되,
                # 최신 점의 X를 KRX 공식 누적값 위치로 offset 평행이동 → 테이블과 부호·크기 정합.
                # (곱셈 스케일은 일별 vs 공식 부호가 반대일 때 궤적이 뒤집혀
                #  '−금액인데 적극매집' 모순이 생김. 연기금은 부호가 어긋날 수 있어 offset 사용)
                snap_latest = sum(flows[N - w : N]) if N >= w else 0
                canon = grp_canon[g][period]
                offset_x = (canon - snap_latest) / mc * 100

                trail = []
                for pt in range(npts - 1, -1, -1):  # oldest → newest
                    end_idx = N - pt * step
                    if end_idx < w:
                        continue

                    window_flow = sum(flows[end_idx - w : end_idx])
                    x = window_flow / mc * 100 + offset_x

                    if period == "1d" or sub >= w:
                        y = 0
                    else:
                        recent = sum(flows[end_idx - sub : end_idx])
                        rest = window_flow - recent
                        rest_days = w - sub
                        recent_rate = recent / sub
                        rest_rate = rest / rest_days if rest_days > 0 else 0
                        y = (recent_rate - rest_rate) / mc * 100 * w

                    trail.append([round(x, 1), round(y, 1)])

                if not trail:
                    continue  # 스냅샷 부족으로 좌표 못 만든 섹터는 제외 (컴포넌트 크래시 방지)

                period_data.append({
                    "n": g,
                    "l": large,
                    "t": trail,
                    "f": round(canon),  # 테이블과 동일한 KRX 공식 누적값
                })

            level_result[period] = period_data
        return level_result

    # 구조: { investor: { large: {period: [...]}, mid: {period: [...]} } }
    result = {}
    for inv, flows in INVESTOR_FLOWS.items():
        stored = INVESTOR_STORED[inv]
        result[inv] = {
            "large": build_level("large", flows, stored),
            "mid": build_level("mid", flows, stored),
        }

    # 4. 저장
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, separators=(",", ":"))

    total = sum(len(p) for inv in result.values() for lvl in inv.values() for p in lvl.values())
    print(
        f"Saved {OUTPUT} ({len(result)} investors × "
        f"large {len(result['combined']['large']['1m'])} · mid {len(result['combined']['mid']['1m'])} sectors/period, "
        f"{total} entries)"
    )


if __name__ == "__main__":
    main()
