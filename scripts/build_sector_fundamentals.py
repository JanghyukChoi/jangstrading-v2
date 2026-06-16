"""
build_sector_fundamentals.py ─ 섹터(대분류·중분류·테마) 펀더멘털 시계열 생성

각 섹터별 월간: 시총·순이익(TTM)·자기자본·PER·PBR·ROE + 가격지수 vs 실적지수(둘다 100 기준).
→ "가격이 실적을 받쳐주나 / 밸류에이션이 확장·축소되나"를 시각화.

입력: scripts/hist_monthly.json (EPS·BPS·주식수 백필 완료 필요)
출력: public/data/sector-fundamentals.json
실행: python scripts/build_sector_fundamentals.py
"""
import json
from pathlib import Path
from collections import defaultdict

BASE = Path(__file__).resolve().parent.parent
HIST = BASE / "scripts" / "hist_monthly.json"
SECTOR_MAP = BASE / "public" / "data" / "sector-map.json"
THEME_MAP = BASE / "public" / "data" / "theme-map.json"
OUT = BASE / "public" / "data" / "sector-fundamentals.json"
THEME_MIN_MEMBERS = 5   # 테마 노이즈/용량 컷


def split_adj_ret(c0, c1, sh0, sh1, m0, m1):
    if not c0 or not c1 or c0 <= 0:
        return None
    if sh0 and sh1 and sh0 > 0:
        sr = sh1 / sh0
        if (sr >= 1.3 or sr <= 0.77) and m0 and m1 and m0 > 0:
            return m1 / m0 - 1
    return c1 / c0 - 1


def build_series(mem, hist, months):
    """한 섹터(멤버 ticker 집합)의 월간 펀더멘털 시계열."""
    mem = set(mem)
    dates, mcap, netinc = [], [], []
    per, roe, pidx, eidx = [], [], [], []
    prev = {}
    idx = 100.0
    base_earn = None
    started = False
    for ym in months:
        px = hist["data"][ym]["px"]
        mc = e = b = 0.0
        rn = rd = 0.0
        cur = {}
        for t in mem:
            v = px.get(t)
            if not v:
                continue
            m = v.get("m", 0); sh = v.get("sh", 0); eps = v.get("eps", 0); bps = v.get("bps", 0); c = v.get("c")
            if not (m and sh):
                continue
            mc += m / 10000.0
            e += eps * sh / 1e12
            b += bps * sh / 1e12
            cur[t] = (c, sh, m)
            if t in prev:
                c0, sh0, m0 = prev[t]
                r = split_adj_ret(c0, c, sh0, sh, m0, m)
                if r is not None:
                    rn += m0 * r; rd += m0
        if mc <= 0:
            prev = cur
            continue
        if started and rd > 0:
            r = max(-0.4, min(0.4, rn / rd))   # 섹터 월수익률 클램프(글리치 방지)
            idx *= (1 + r)
        started = True
        if base_earn is None and e > 0:
            base_earn = e
        dates.append(ym)
        mcap.append(round(mc, 1))
        netinc.append(round(e, 2))
        per.append(round(mc / e, 1) if e > 0 else None)
        roe.append(round(e / b * 100, 1) if b > 0 else None)
        pidx.append(round(idx, 1))
        eidx.append(round(e / base_earn * 100, 1) if base_earn else None)
        prev = cur

    if len(dates) < 24:
        return None
    # 분기 샘플링(매 3개월 + 마지막) — 10년 차트 용량 절감
    n = len(dates)
    keep = [i for i in range(n) if i % 3 == 0]
    if keep[-1] != n - 1:
        keep.append(n - 1)
    pick = lambda a: [a[i] for i in keep]
    return {"dates": pick(dates), "mcap": pick(mcap), "netinc": pick(netinc),
            "per": pick(per), "roe": pick(roe), "priceIdx": pick(pidx), "earnIdx": pick(eidx)}


def main():
    hist = json.load(open(HIST))
    sm = json.load(open(SECTOR_MAP))
    tm = json.load(open(THEME_MAP))
    months = sorted(hist["data"])

    # 레벨별 멤버 구성
    members_by_level = {"large": defaultdict(list), "mid": defaultdict(list), "theme": {}}
    for t, v in sm.items():
        for f in ("large", "mid"):
            g = v.get(f)
            if g and g != "기타":
                members_by_level[f][g].append(t)
    for theme, tickers in tm.items():
        if len(tickers) >= THEME_MIN_MEMBERS:
            members_by_level["theme"][theme] = tickers

    levels = {"large": {}, "mid": {}, "theme": {}}
    for lvl, groups in members_by_level.items():
        for sec, mem in groups.items():
            s = build_series(mem, hist, months)
            if s:
                levels[lvl][sec] = s

    out = {"asof": months[-1], "levels": levels}
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    sz = OUT.stat().st_size / 1024
    print(f"Saved {OUT} ({sz:.0f} KB) · 대분류 {len(levels['large'])} · 중분류 {len(levels['mid'])} · 테마 {len(levels['theme'])} · {months[0]}~{months[-1]}")


if __name__ == "__main__":
    main()
