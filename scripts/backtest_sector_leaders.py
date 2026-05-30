"""
섹터 내 주도주/급부상 백테스트 (sector-relative)

문제: 사이트의 섹터 페이지 "주도주/급부상" 태그가 한 번도 검증된 적 없음.
- 옛 로직: nMom 35% + nShare 25% + nInt 20% + nAccel 20%, p75 + share >= 3%
- 백테스트로 "태그 받은 종목이 진짜 outperform 하는지" 검증.

새 점수 (V3 정신):
- 35% bps (외인+기관 60일 시총대비)
- 20% 가격 60일 모멘텀
- 20% 거래량 20일 surge
- 25% 가속도 (5d/20d)
- 모두 섹터 내 백분위 (cross-sectional within sector)

태그:
- 주도주: composite ≥ p75 + flow > 0
- 급부상: composite ≥ p50 (and < p75) + accel > 1.5 + flow > 0
- 소외: flow ≤ 0

입력: scripts/backtest_data/timeseries (10년치)
      public/data/stock-rankings.json (ticker → sector_mid)
출력: 콘솔 — leader/emerging tag별 성과 + 옛 로직 비교

실행:
  python scripts/backtest_sector_leaders.py
"""

import json
import statistics
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TS_DIR = BASE_DIR / "scripts" / "backtest_data" / "timeseries"
RANKINGS_PATH = BASE_DIR / "public" / "data" / "stock-rankings.json"

sys.path.insert(0, str(BASE_DIR / "scripts"))
from backtest_signals import (  # noqa: E402
    safe_sum,
    _flow_bps,
    _mcap_at,
    _tv_surge,
)

TC_ROUNDTRIP = 0.005
FORWARD_WINDOWS = [5, 20]
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


def load_sector_map():
    """ticker → sector_mid 매핑. 라이브 stock-rankings.json 기반.
    백테스트는 sector 정보가 시점별로 일정하다고 가정."""
    r = json.load(open(RANKINGS_PATH, "r", encoding="utf-8"))
    mp = {}
    for s in r["data"]:
        t = s.get("ticker")
        if not t:
            continue
        mid = s.get("sector_mid") or s.get("sector")
        if mid and mid != "기타":
            mp[t] = mid
    return mp


# ───────────────────────────────────────────────────────────
# Score components per stock
# ───────────────────────────────────────────────────────────

def score_components(data, idx):
    """한 종목, 한 시점의 점수 컴포넌트 dict 반환. None이면 후보 제외."""
    f = data.get("foreign", [])
    inst = data.get("inst", [])
    p = data.get("prices", [])
    if idx < 60 or idx >= len(f) or idx >= len(p):
        return None

    mcap = _mcap_at(data, idx)
    if mcap is None or mcap < 30_000_000_000:  # 시총 300억 미만 제외
        return None

    f60 = safe_sum(f, idx - 60, idx)
    i60 = safe_sum(inst, idx - 60, idx)
    if f60 is None or i60 is None:
        return None
    flow_60 = f60 + i60
    bps_60d = _flow_bps(flow_60, mcap)
    if bps_60d is None:
        return None

    p_now = p[idx]
    p_60 = p[idx - 60] if idx - 60 >= 0 else None
    if not p_now or p_now <= 0 or not p_60 or p_60 <= 0:
        return None
    price_mom = p_now / p_60 - 1

    surge = _tv_surge(data, idx, 20)
    if surge is None:
        surge = 0

    f5 = safe_sum(f, idx - 5, idx)
    i5 = safe_sum(inst, idx - 5, idx)
    f20 = safe_sum(f, idx - 20, idx)
    i20 = safe_sum(inst, idx - 20, idx)
    if any(x is None for x in [f5, i5, f20, i20]):
        return None
    combined5 = f5 + i5
    combined20 = f20 + i20
    accel = (combined5 / 5) / (combined20 / 20) if combined20 > 0 else 0

    return {
        "bps": bps_60d,
        "price_mom": price_mom,
        "vol_surge": surge,
        "accel": max(accel, 0),
        "flow_pos": flow_60 > 0,
    }


def pct_rank(values, val):
    """배열에서 val의 백분위 (0~100)"""
    if len(values) <= 1:
        return 50
    below = sum(1 for v in values if v < val)
    return below / (len(values) - 1) * 100


# ───────────────────────────────────────────────────────────
# Old logic (사이트 현재 로직)
# ───────────────────────────────────────────────────────────

def old_logic_components(data, idx):
    """옛 cls 로직 컴포넌트. nMom 35% + nShare 25% + nInt 20% + nAccel 20%."""
    f = data.get("foreign", [])
    inst = data.get("inst", [])
    p = data.get("prices", [])
    if idx < 20 or idx >= len(f) or idx >= len(p):
        return None

    mcap = _mcap_at(data, idx)
    # 옛 로직: 시총 필터 없음, 그냥 일부만 (cap_won > 0)
    if mcap is None or mcap <= 0:
        return None

    # period = "1m" → 20일
    f20 = safe_sum(f, idx - 20, idx)
    i20 = safe_sum(inst, idx - 20, idx)
    if f20 is None or i20 is None:
        return None
    flow = f20 + i20

    intensity = (flow / mcap) * 100 * 1_000_000  # 시총대비 % (옛 사이트 공식과 동일)

    p_now = p[idx]
    p_20 = p[idx - 20] if idx - 20 >= 0 else None
    if not p_now or p_now <= 0 or not p_20 or p_20 <= 0:
        return None
    price_mom = p_now / p_20 - 1

    f5 = safe_sum(f, idx - 5, idx)
    i5 = safe_sum(inst, idx - 5, idx)
    if f5 is None or i5 is None:
        return None
    combined5 = f5 + i5
    dw = combined5 / 5
    dm = flow / 20
    accel = dw / dm if dm != 0 else (2 if dw > 0 else 0)

    return {
        "flow": flow,
        "intensity": intensity,
        "price_mom": price_mom,
        "accel": accel,
        "mcap": mcap,
    }


# ───────────────────────────────────────────────────────────
# Backtest engine
# ───────────────────────────────────────────────────────────

def run_backtest(timeseries, sector_map, score_func, tag_func, label):
    """
    score_func: (data, idx) -> dict | None
    tag_func: (components, sector_items_components) -> "leader" | "emerging" | None

    sector_items_components = [{components dict for each item in same sector}]
    """
    print(f"\n[{label}] backtest 시작")
    all_dates_seen = set()
    for d in timeseries.values():
        all_dates_seen.update(d.get("dates", []))
    all_dates = sorted(all_dates_seen)
    eval_dates = all_dates[:-20] if len(all_dates) > 20 else []

    results_by_tag = {"leader": [], "emerging": []}
    t0 = time.time()

    for date in eval_dates:
        # 1. 모든 종목 score 계산
        scores = {}  # ticker -> components
        for ticker, data in timeseries.items():
            try:
                idx = data["dates"].index(date)
            except ValueError:
                continue
            sc = score_func(data, idx)
            if sc is not None:
                scores[ticker] = (sc, idx)

        # 2. 섹터별 그룹핑
        sector_groups = {}
        for ticker, (sc, idx) in scores.items():
            sec = sector_map.get(ticker)
            if not sec:
                continue
            sector_groups.setdefault(sec, []).append((ticker, sc, idx))

        # 3. 각 섹터에서 tag 결정
        for sec, items in sector_groups.items():
            if len(items) < 5:
                continue
            comps = [sc for _, sc, _ in items]
            for ticker, sc, idx in items:
                tag = tag_func(sc, comps)
                if tag is None:
                    continue

                # forward return 측정
                data = timeseries[ticker]
                prices = data.get("prices", [])
                if idx >= len(prices) or not prices[idx] or prices[idx] <= 0:
                    continue
                p_now = prices[idx]
                row = {"date": date, "ticker": ticker, "sector": sec, "tag": tag}
                for w in FORWARD_WINDOWS:
                    fi = idx + w
                    if fi < len(prices) and prices[fi] and prices[fi] > 0:
                        row[f"ret{w}"] = prices[fi] / p_now - 1
                    else:
                        row[f"ret{w}"] = None
                results_by_tag[tag].append(row)

    elapsed = time.time() - t0
    n_leader = len(results_by_tag["leader"])
    n_emerging = len(results_by_tag["emerging"])
    print(f"  leader: {n_leader:,} events / emerging: {n_emerging:,} events ({elapsed:.1f}s)")
    return results_by_tag


# ───────────────────────────────────────────────────────────
# Tag functions
# ───────────────────────────────────────────────────────────

def tag_new(sc, sector_comps):
    """새 로직 — V3 정신 (bps + mom + surge + accel)"""
    if not sc.get("flow_pos"):
        return None  # 소외
    bps_vals = [c["bps"] for c in sector_comps]
    mom_vals = [c["price_mom"] for c in sector_comps]
    surge_vals = [c["vol_surge"] for c in sector_comps]
    accel_vals = [c["accel"] for c in sector_comps]

    bps_pct = pct_rank(bps_vals, sc["bps"])
    mom_pct = pct_rank(mom_vals, sc["price_mom"])
    surge_pct = pct_rank(surge_vals, sc["vol_surge"])
    accel_pct = pct_rank(accel_vals, sc["accel"])

    composite = 0.35 * bps_pct + 0.20 * mom_pct + 0.20 * surge_pct + 0.25 * accel_pct

    # p75/p50 by sector
    pos_comps = [c for c in sector_comps if c.get("flow_pos")]
    if not pos_comps:
        return None
    other_composites = []
    for c in pos_comps:
        bp = pct_rank(bps_vals, c["bps"])
        mp = pct_rank(mom_vals, c["price_mom"])
        sp = pct_rank(surge_vals, c["vol_surge"])
        ap = pct_rank(accel_vals, c["accel"])
        other_composites.append(0.35 * bp + 0.20 * mp + 0.20 * sp + 0.25 * ap)
    other_composites.sort()
    p75 = other_composites[int(len(other_composites) * 0.75)] if other_composites else 75
    p50 = other_composites[int(len(other_composites) * 0.50)] if other_composites else 50

    if composite >= p75 and sc["bps"] >= 10:
        return "leader"
    if composite >= p50 and sc["accel"] >= 1.5 and sc["bps"] >= 0:
        return "emerging"
    return None


def tag_old(sc, sector_comps):
    """옛 로직 — nMom 35% + nShare 25% + nInt 20% + nAccel 20%"""
    if sc["flow"] <= 0:
        return None

    total_pos = sum(max(c["flow"], 0) for c in sector_comps)
    if total_pos <= 0:
        return None
    share = max(sc["flow"], 0) / total_pos * 100

    int_vals = [c["intensity"] for c in sector_comps]
    mom_vals = [c["price_mom"] for c in sector_comps]
    n_int = pct_rank(int_vals, sc["intensity"])
    n_mom = pct_rank(mom_vals, sc["price_mom"])
    n_share = min(share * 5, 100)
    n_accel = min(max(sc["accel"], 0) * 50, 100)

    cls = 0.25 * n_share + 0.20 * n_int + 0.35 * n_mom + 0.20 * n_accel

    pos_comps = [c for c in sector_comps if c["flow"] > 0]
    other_cls = []
    for c in pos_comps:
        sh = max(c["flow"], 0) / total_pos * 100
        n_sh = min(sh * 5, 100)
        ni = pct_rank(int_vals, c["intensity"])
        nm = pct_rank(mom_vals, c["price_mom"])
        na = min(max(c["accel"], 0) * 50, 100)
        other_cls.append(0.25 * n_sh + 0.20 * ni + 0.35 * nm + 0.20 * na)
    other_cls.sort()
    p75 = other_cls[int(len(other_cls) * 0.75)] if other_cls else 75
    p50 = other_cls[int(len(other_cls) * 0.50)] if other_cls else 50

    if cls >= p75 and share >= 3:
        return "leader"
    if cls >= p50 and sc["accel"] > 1.2:
        return "emerging"
    return None


# ───────────────────────────────────────────────────────────
# Metrics
# ───────────────────────────────────────────────────────────

def compute_metrics(results, window=20):
    key = f"ret{window}"
    valid = [r[key] for r in results if r.get(key) is not None]
    if not valid:
        return None
    n = len(valid)
    avg = statistics.mean(valid)
    median = statistics.median(valid)
    hit = sum(1 for r in valid if r > 0) / n
    std = statistics.stdev(valid) if n > 1 else 0
    avg_tc = avg - TC_ROUNDTRIP
    sharpe = (avg / std) * ((250 / window) ** 0.5) if std > 0 else 0
    sharpe_tc = (avg_tc / std) * ((250 / window) ** 0.5) if std > 0 else 0
    t_stat = (avg / (std / (n ** 0.5))) if std > 0 else 0
    return {"n": n, "avg": avg, "median": median, "hit": hit, "std": std,
            "avg_tc": avg_tc, "sharpe": sharpe, "sharpe_tc": sharpe_tc, "t_stat": t_stat}


def regime_split(results, window=20):
    out = {}
    for name, s, e in REGIMES:
        sub = [r for r in results if s <= r["date"] <= e]
        out[name] = compute_metrics(sub, window)
    return out


def train_test_split(results, train_end, window=20):
    train = [r for r in results if r["date"] <= train_end]
    test = [r for r in results if r["date"] > train_end]
    return compute_metrics(train, window), compute_metrics(test, window)


def fmt_pct(v):
    return f"{v*100:+6.2f}%" if v is not None else "  -  "


def report(results_by_tag, label):
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}")
    for tag in ["leader", "emerging"]:
        rows = results_by_tag[tag]
        if not rows:
            print(f"\n  [{tag}] NO RESULTS")
            continue
        m20 = compute_metrics(rows, 20)
        m5 = compute_metrics(rows, 5)
        print(f"\n  [{tag}] N={m20['n']:,}")
        print(f"    5d:  avg={fmt_pct(m5['avg'])}  TC={fmt_pct(m5['avg_tc'])}  hit={m5['hit']*100:5.1f}%  t={m5['t_stat']:5.2f}")
        print(f"    20d: avg={fmt_pct(m20['avg'])}  TC={fmt_pct(m20['avg_tc'])}  hit={m20['hit']*100:5.1f}%  t={m20['t_stat']:5.2f}")
        tr, te = train_test_split(rows, TRAIN_END_DATE, 20)
        if tr and te:
            print(f"    Walk-fwd: Train avg={fmt_pct(tr['avg'])} hit={tr['hit']*100:.1f}% | Test avg={fmt_pct(te['avg'])} hit={te['hit']*100:.1f}%")
        rs = regime_split(rows, 20)
        print(f"    Regime:")
        for rn, rm in rs.items():
            if rm:
                print(f"      [{rn:10s}] N={rm['n']:>5d} avg={fmt_pct(rm['avg'])} hit={rm['hit']*100:5.1f}%")


def main():
    ts = load_timeseries()
    sector_map = load_sector_map()
    print(f"  sector map: {len(sector_map)} tickers (excluding 기타)")

    # 새 로직
    new_results = run_backtest(ts, sector_map, score_components, tag_new, "NEW (V3 정신)")
    report(new_results, "NEW sector-relative")

    # 옛 로직
    old_results = run_backtest(ts, sector_map, old_logic_components, tag_old, "OLD (현재 사이트)")
    report(old_results, "OLD sector-relative (현재 사이트 로직)")


if __name__ == "__main__":
    main()
