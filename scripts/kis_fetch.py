"""
KIS Open API 로 전 종목 수급/시세/재무를 수집해 stock-rankings.json 을 만든다.

기존 파이프라인의 fetch_data.py + add_tickers.py + add_fundamentals.py +
add_price_changes.py + add_avg_cost.py + add_inst_detail.py 를 한 번에 대체한다.
KIS 의 "종목별 투자자매매동향(일별)" 이 한 호출에 30 영업일치의
외국인/기관/개인/기타 + 기관 세부 8 주체 + OHLCV 를 전부 주기 때문이다.

출력 스키마는 기존 stock-rankings.json 과 동일하다. 다운스트림
(build_timeseries / build_v3_signals / build_market_signals / build_regime /
build_rrg / generate_report / send_telegram) 은 손대지 않는다.

종목당 호출 수:
  - 수급+시세: depth 회 (기본 5 = 150 영업일. 6m(120영업일) 수익률을 내려면
               기준일 포함 121 행이 필요해서 4 회로는 모자란다)
  - 재무:      1 회 (PER/PBR/EPS/BPS/시총)
  => 전 종목 약 16,300 회, 초당 6 건 기준 약 45 분

실행:
  python scripts/kis_fetch.py                    # 전 종목
  python scripts/kis_fetch.py --limit 30         # 테스트
  python scripts/kis_fetch.py --date 20260911    # 기준일 지정
  python scripts/kis_fetch.py --no-cache         # 캐시 무시하고 새로 받기
"""

import argparse
import io
import json
import sys
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cost_basis as cb  # noqa: E402
from kis_api import KisClient, KisError  # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "public" / "data"
CACHE_DIR = BASE_DIR / ".kis_cache"

INVESTOR_URL = "/uapi/domestic-stock/v1/quotations/investor-trade-by-stock-daily"
INVESTOR_TR = "FHPTJ04160001"
PRICE_URL = "/uapi/domestic-stock/v1/quotations/inquire-price"
PRICE_TR = "FHKST01010100"
MARKET_URL = "/uapi/domestic-stock/v1/quotations/inquire-investor-daily-by-market"
MARKET_TR = "FHPTJ04040000"

# 시장별 투자자매매동향 파라미터. FID_INPUT_ISCD_2 를 비워두면 대금이 전부 0 으로
# 내려온다(실측). 업종분류코드를 그대로 넣어야 한다.
MARKETS = {
    "KOSPI": {"iscd": "0001", "code": "KSP"},
    "KOSDAQ": {"iscd": "1001", "code": "KSQ"},
}

# 스냅샷 보관 영업일 수 (save_snapshot.py 와 동일)
MAX_SNAPSHOTS = 500

MASTER = {
    "KOSPI": ("https://new.real.download.dws.co.kr/common/master/kospi_code.mst.zip", 228),
    "KOSDAQ": ("https://new.real.download.dws.co.kr/common/master/kosdaq_code.mst.zip", 222),
}

# 기존 fetch_data.py 와 동일한 정의 (영업일 수)
PERIODS = {"1d": 1, "1w": 5, "1m": 20, "3m": 60, "6m": 120}

# 한 호출이 돌려주는 영업일 수 (실측)
ROWS_PER_CALL = 30

# 기관 세부 주체: 출력 라벨 -> KIS 순매수 수량/대금 필드 접두사
INST_DETAIL = {
    "금융투자": "scrt",
    "보험": "insu",
    "투신": "ivtr",
    "사모": "pe_fund",
    "은행": "bank",
    "연기금": "fund",
}

# 평균단가 계산 기간 (영업일)
AVG_COST_LOOKBACK = 120


COST_BASIS_PATH = DATA_DIR / "cost-basis.json"


def load_cost_basis():
    """build_cost_basis.py 가 만든 기준가격 상태. 없으면 빈 상태로 시작한다."""
    try:
        raw = json.loads(COST_BASIS_PATH.read_text(encoding="utf-8"))
        return raw.get("data", {}), raw.get("updated_through", "")
    except (OSError, ValueError):
        return {}, ""


def save_cost_basis(state, date_iso):
    try:
        COST_BASIS_PATH.write_text(
            json.dumps({"updated_through": date_iso, "data": state}, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError as e:
        print(f"  ⚠️ cost-basis.json 저장 실패(무시): {e}")


def update_cost_basis(entry, rows, holdings, shares, since_ymd):
    """종목의 기준가격 상태를 since_ymd 이후 날짜로 전진시킨다.

    상태가 없으면(신규 상장 등) 가진 이력 전체로 새로 만든다. 이력이 짧으면
    그만큼 기준가격이 현재가 쪽으로 치우치지만, 시작 보유량을 0 으로 놓던
    기존 방식보다는 낫다.
    """
    # 상태 파일은 날짜를 ISO("2026-09-14")로, KIS row 는 "20260914"로 쓴다.
    # 그대로 문자열 비교하면 '0' > '-' 라 항상 참이 되어 매일 전체 이력이 다시
    # 적용된다(기준가격이 오염된다). 형식을 맞춰서 비교한다.
    cutoff = (since_ymd or "").replace("-", "")
    new_rows = [r for r in rows if not cutoff or r["stck_bsop_date"] > cutoff]
    if entry is None:
        entry = {}
        new_rows = rows  # 처음 만드는 종목은 전체 이력으로

    if not new_rows:
        return entry

    for group, key in (("foreign", "f"), ("institution", "i")):
        prefix = cb.GROUPS[group]
        series = cb._series(new_rows, prefix)
        # 외국인 보유량 경로는 '현재 보유량'에서 역산하므로 새 구간에도 그대로 성립
        holdings_path = (
            cb._holdings_path(series, holdings)
            if group == "foreign" and holdings > 0
            else [0] * len(series)
        )
        st = entry.get(key) or cb.new_state()
        for i, r in enumerate(new_rows):
            ex = cb.exit_rate_for(group, r, series[i], holdings_path[i], shares)
            cb.advance(st, ex, series[i]["buy"], series[i]["price"])
        if st["d"] > 0:
            entry[key] = st
    return entry


def cost_basis_to_avg_cost(entry, close):
    """기존 avg_cost 스키마 그대로 내보낸다.

    프론트(app/stocks/[ticker]/page.tsx)가 이 형태를 직접 읽는다. 계산만 바뀌고
    구조는 그대로여야 화면이 안 깨진다. avg_cost 는 회전율 가중 기준가격,
    pnl_pct 는 CGO(미실현 손익률).
    """
    if not entry or close <= 0:
        return None
    out = {"price": close}
    for key, label in (("f", "foreign"), ("i", "institution")):
        s = cb.summarize(entry.get(key), close)
        if s:
            out[label] = {"avg_cost": s["reference"], "pnl_pct": s["cgo"]}
    return out if len(out) > 1 else None


OHLC_DIR = DATA_DIR / "ohlc"
OHLC_KEEP = 250  # 보관 영업일 (약 1년)


def append_ohlc(ticker, rows, basis=None):
    """일봉 파일에 새 날짜만 덧붙인다. 파일이 없으면 가진 만큼으로 새로 만든다.

    차트용 데이터는 timeseries 와 분리해 둔다. 합치면 종목 상세 페이지가
    받는 파일이 2~3 배가 되어 차트를 안 여는 사람까지 느려진다.
    scripts/build_ohlc.py 가 만든 포맷(병렬 배열, 날짜 YYMMDD)을 그대로 쓴다.
    """
    path = OHLC_DIR / f"{ticker}.json"
    try:
        cur = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cur = {"t": ticker, "d": [], "o": [], "h": [], "l": [], "c": [], "v": []}

    have = set(cur["d"])
    added = 0
    for r in rows:
        ymd = r.get("stck_bsop_date", "")
        if len(ymd) != 8:
            continue
        key = int(ymd[2:])
        if key in have:
            continue
        c = to_int(r.get("stck_clpr"))
        if c <= 0:
            continue
        cur["d"].append(key)
        cur["o"].append(to_int(r.get("stck_oprc")))
        cur["h"].append(to_int(r.get("stck_hgpr")))
        cur["l"].append(to_int(r.get("stck_lwpr")))
        cur["c"].append(c)
        cur["v"].append(to_int(r.get("acml_vol")))
        have.add(key)
        added += 1

    if not cur["d"]:
        return 0

    # 날짜 오름차순 정렬 후 보관 기간만 남긴다
    order = sorted(range(len(cur["d"])), key=lambda i: cur["d"][i])[-OHLC_KEEP:]
    for k in ("d", "o", "h", "l", "c", "v"):
        cur[k] = [cur[k][i] for i in order]

    # 매물대(가격 구간별 비중)를 같은 파일에 넣는다. 종목당 361바이트라
    # 차트가 이미 받는 파일에 얹으면 추가 요청이 없다.
    # cost-basis.json 은 3.9MB 라 클라이언트가 통째로 받을 수 없다.
    if basis:
        for key in ("fb", "ib"):
            cur.pop(key, None)
        if basis.get("f"):
            cur["fb"] = [[b["price"], b["weight"]] for b in basis["f"]]
        if basis.get("i"):
            cur["ib"] = [[b["price"], b["weight"]] for b in basis["i"]]

    OHLC_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cur, separators=(",", ":")), encoding="utf-8")
    return added


def load_dividends():
    """kis_dividends.py 가 만든 주당배당금 표. 없으면 빈 dict."""
    path = DATA_DIR / "dividends.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("data", {})
    except (OSError, ValueError):
        return {}


def to_int(v):
    """KIS 는 정수 필드도 "6564.00" 처럼 소수 문자열로 주는 경우가 있다."""
    try:
        return int(float(str(v).strip() or 0))
    except (TypeError, ValueError):
        return 0


def to_float(v):
    try:
        return float(str(v).strip() or 0)
    except (TypeError, ValueError):
        return 0.0


def ntby_pbmn(row, prefix):
    """주체별 순매수 '대금'(백만원). KIS 는 접미사가 주체마다 다르다."""
    for suffix in ("_ntby_tr_pbmn", "_ntby_pbmn"):
        key = prefix + suffix
        if key in row:
            return to_int(row[key])
    return 0


def ntby_qty(row, prefix):
    """주체별 순매수 '수량'. 접미사가 _ntby_qty 인 것과 _ntby_vol 인 것이 섞여 있다."""
    for suffix in ("_ntby_qty", "_ntby_vol"):
        key = prefix + suffix
        if key in row:
            return to_int(row[key])
    return 0


# ─── 종목 유니버스 ──────────────────────────────────────────────────
def load_universe(limit=None):
    """KIS 종목 마스터에서 (ticker, name, market) 목록. 인증 불필요."""
    universe = []
    for market, (url, tail) in MASTER.items():
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        z = zipfile.ZipFile(io.BytesIO(resp.content))
        raw = z.read(z.namelist()[0]).decode("cp949", errors="replace")

        count = 0
        for line in raw.splitlines():
            if not line.strip():
                continue
            head = line[: len(line) - tail]
            rest = line[len(line) - tail :]
            code = head[0:9].rstrip()
            name = head[21:].strip()
            # rest[1:3] == "ST" 가 주권. ETF/ETN/리츠/펀드는 제외.
            if rest[1:3] != "ST" or len(code) != 6:
                continue
            universe.append({"ticker": code, "name": name, "market": market})
            count += 1
        print(f"  {market}: {count}종목")

    universe.sort(key=lambda x: x["ticker"])
    if limit:
        universe = universe[:limit]
    return universe


# ─── 수집 ───────────────────────────────────────────────────────────
def fetch_history(kis, ticker, end_date, depth, cache=True):
    """종목의 일별 투자자매매동향 + OHLCV 를 depth 회 거슬러 올라가며 모은다.

    Returns: 날짜 오름차순 row 리스트
    """
    cache_file = CACHE_DIR / f"{ticker}_{end_date}_{depth}.json"
    if cache and cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except ValueError:
            pass

    seen = {}
    cursor = end_date
    for _ in range(depth):
        body = kis.get(
            INVESTOR_URL,
            tr_id=INVESTOR_TR,
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": ticker,
                "FID_INPUT_DATE_1": cursor,
                "FID_ORG_ADJ_PRC": "",
                "FID_ETC_CLS_CODE": "",
            },
        )
        rows = body.get("output2") or []
        if isinstance(rows, dict):
            rows = [rows]
        # 종가가 비어 있으면 실제로 거래된 종목이 아니다 (없는 코드 등)
        rows = [r for r in rows if str(r.get("stck_clpr", "")).strip()]
        if not rows:
            break

        for r in rows:
            seen[r["stck_bsop_date"]] = r

        oldest = min(r["stck_bsop_date"] for r in rows)
        cursor = (datetime.strptime(oldest, "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d")

    out = [seen[d] for d in sorted(seen)]
    if cache and out:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


def fetch_fundamentals(kis, ticker, end_date, cache=True):
    """PER/PBR/EPS/BPS/시가총액. inquire-price 는 '현재' 기준이라 장 마감 후 호출."""
    cache_file = CACHE_DIR / f"fund_{ticker}_{end_date}.json"
    if cache and cache_file.exists():
        try:
            return json.loads(cache_file.read_text(encoding="utf-8"))
        except ValueError:
            pass

    body = kis.get(
        PRICE_URL,
        tr_id=PRICE_TR,
        params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": ticker},
    )
    out = body.get("output") or {}
    if cache and out:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return out


# ─── 집계 ───────────────────────────────────────────────────────────
def aggregate_flows(rows):
    """기간별 외국인/기관/합계/기타법인 순매수 대금(백만원) 과 기관 세부주체.

    기타법인(etc_corp)은 KRX 분류에서 금융기관이 아닌 일반 법인이다. 자사주
    매입, 계열사 지분 매입, M&A 지분 축적이 여기 들어간다 — 공개 데이터에서
    내부자에 가장 가까운 매수 주체인데 어느 사이트도 보여주지 않는다.
    같은 응답에 이미 있어서 추가 호출이 없다.

    값은 이미 백만원 단위 정수라 float 로 부풀리지 않는다. 0 인 항목은 아예
    빼서 파일 크기를 줄인다 (기존 파이프라인도 같은 방식이었고, 프론트는
    `Object.entries` 순회와 `?? 0` 으로 키 누락을 그대로 견딘다).
    inst_detail 항목의 58%, pension 의 66% 가 0 이다.
    """
    foreign, institution, combined = {}, {}, {}
    inst_detail, pension, corp = {}, {}, {}

    for period, n in PERIODS.items():
        window = rows[-n:] if n <= len(rows) else rows
        f = sum(ntby_pbmn(r, "frgn") for r in window)
        i = sum(ntby_pbmn(r, "orgn") for r in window)
        foreign[period] = f
        institution[period] = i
        combined[period] = f + i
        c = sum(ntby_pbmn(r, "etc_corp") for r in window)
        if c:
            corp[period] = c

        detail = {}
        for label, prefix in INST_DETAIL.items():
            v = sum(ntby_pbmn(r, prefix) for r in window)
            if v:
                detail[label] = v
        if detail:
            inst_detail[period] = detail
        if detail.get("연기금"):
            pension[period] = detail["연기금"]

    return foreign, institution, combined, inst_detail, pension, corp


def aggregate_price_changes(rows):
    """기간별 수익률(%). 기준일 종가 대비 n 영업일 전 종가."""
    if not rows:
        return {p: None for p in PERIODS}
    last = to_float(rows[-1].get("stck_clpr"))
    out = {}
    for period, n in PERIODS.items():
        idx = len(rows) - 1 - n
        if last <= 0 or idx < 0:
            out[period] = None
            continue
        base = to_float(rows[idx].get("stck_clpr"))
        out[period] = round((last - base) / base * 100, 2) if base > 0 else None
    return out


def calc_avg_cost(rows, prefix):
    """이동평균 원가법 추정 평균단가. add_avg_cost.py 와 동일한 알고리즘."""
    avg_cost = 0.0
    position = 0

    for r in rows[-AVG_COST_LOOKBACK:]:
        vol = to_int(r.get("acml_vol"))
        amount = to_int(r.get("acml_tr_pbmn"))  # 원 단위
        vwap = (amount / vol) if vol > 0 else 0
        if vwap <= 0:
            continue

        net_vol = ntby_qty(r, prefix)
        if net_vol > 0:
            total = avg_cost * position + vwap * net_vol
            position += net_vol
            if position > 0:
                avg_cost = total / position
        elif net_vol < 0:
            position += net_vol
            if position <= 0:
                avg_cost = 0.0
                position = 0

    if position <= 0 or avg_cost <= 0:
        return None
    return round(avg_cost, 0)


def build_avg_cost(rows):
    if not rows:
        return None
    price = to_float(rows[-1].get("stck_clpr"))
    if price <= 0:
        return None

    out = {"price": price}
    for label, prefix in (("foreign", "frgn"), ("institution", "orgn")):
        cost = calc_avg_cost(rows, prefix)
        if cost:
            out[label] = {
                "avg_cost": int(cost),
                "pnl_pct": round((price - cost) / cost * 100, 2),
            }
    return out if len(out) > 1 else None


# ─── 시장 단위 ──────────────────────────────────────────────────────
def fetch_market(kis, date_str):
    """시장별 투자자매매동향(일별). 한 호출에 300 영업일치 + 지수가 같이 온다."""
    out = {}
    for market, cfg in MARKETS.items():
        body = kis.get(
            MARKET_URL,
            tr_id=MARKET_TR,
            params={
                "FID_COND_MRKT_DIV_CODE": "U",
                "FID_INPUT_ISCD": cfg["iscd"],
                "FID_INPUT_DATE_1": date_str,
                "FID_INPUT_ISCD_1": cfg["code"],
                "FID_INPUT_DATE_2": date_str,
                "FID_INPUT_ISCD_2": cfg["iscd"],
            },
        )
        rows = body.get("output") or []
        if isinstance(rows, dict):
            rows = [rows]
        rows = [r for r in rows if str(r.get("bstp_nmix_prpr", "")).strip()]
        out[market] = sorted(rows, key=lambda r: r["stck_bsop_date"])
        print(f"  {market}: {len(out[market])}영업일")
    return out


def build_market_overview(market_rows, date_iso, date_str):
    """market-overview.json — 시장별 지수 + 기간별 투자자 자금흐름(백만원)."""
    data = {}
    for market, rows in market_rows.items():
        rows = [r for r in rows if r["stck_bsop_date"] <= date_str]
        if not rows:
            continue
        last = rows[-1]
        flow = {}
        for period, n in PERIODS.items():
            window = rows[-n:] if n <= len(rows) else rows
            flow[period] = {
                "foreign": float(sum(to_int(r.get("frgn_ntby_tr_pbmn")) for r in window)),
                "institution": float(sum(to_int(r.get("orgn_ntby_tr_pbmn")) for r in window)),
                "individual": float(sum(to_int(r.get("prsn_ntby_tr_pbmn")) for r in window)),
            }
        data[market] = {
            "index": to_float(last.get("bstp_nmix_prpr")),
            "change": to_float(last.get("bstp_nmix_prdy_vrss")) or None,
            "change_pct": to_float(last.get("bstp_nmix_prdy_ctrt")) or None,
            "flow": flow,
        }

    path = DATA_DIR / "market-overview.json"
    path.write_text(
        json.dumps({"date": date_iso, "unit": "백만원", "data": data}, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  market-overview.json ({len(data)}개 시장)")
    return data


def build_kospi_history(market_rows, date_str):
    """kospi-history.json — {YYYY-MM-DD: 종가}. 기존 이력은 보존하고 병합한다."""
    path = DATA_DIR / "kospi-history.json"
    history = {}
    if path.exists():
        try:
            history = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            history = {}

    added = 0
    for r in market_rows.get("KOSPI", []):
        d = r["stck_bsop_date"]
        if d > date_str:
            continue
        iso = f"{d[:4]}-{d[4:6]}-{d[6:]}"
        val = to_float(r.get("bstp_nmix_prpr"))
        if val > 0 and iso not in history:
            added += 1
        if val > 0:
            history[iso] = val

    history = {k: history[k] for k in sorted(history)}
    path.write_text(json.dumps(history, ensure_ascii=False), encoding="utf-8")
    print(f"  kospi-history.json ({len(history)}일, 신규 {added}일)")
    return history


def build_snapshot(results, market_data, date_iso):
    """snapshots/YYYY-MM-DD.json — save_snapshot.py + augment_snapshots.py 대체.

    시그널은 build_v3_signals.py 가 timeseries 기반으로 따로 계산하므로
    여기서는 빈 placeholder 만 넣는다(기존과 동일).
    """
    prices, foreign_1d, inst_1d, pension_1d = {}, {}, {}, {}
    indi_1d, corp_1d = {}, {}
    market_cap, trade_value = {}, {}

    for s in results:
        t = s["ticker"]
        if s.get("_close"):
            prices[t] = s["_close"]
        if s.get("_foreign_1d"):
            foreign_1d[t] = round(s["_foreign_1d"], 1)
        if s.get("_inst_1d"):
            inst_1d[t] = round(s["_inst_1d"], 1)
        if s.get("_pension_1d"):
            pension_1d[t] = round(s["_pension_1d"], 1)
        if s.get("_indi_1d"):
            indi_1d[t] = round(s["_indi_1d"], 1)
        if s.get("_corp_1d"):
            corp_1d[t] = round(s["_corp_1d"], 1)
        if s.get("_trade_value"):
            trade_value[t] = s["_trade_value"]
        if s.get("market_cap"):
            # 랭킹의 market_cap 은 억원, 스냅샷은 원 단위
            market_cap[t] = int(s["market_cap"] * 100_000_000)

    breadth = {
        "foreign_buy": sum(1 for s in results if s["foreign"]["1d"] > 0),
        "foreign_sell": sum(1 for s in results if s["foreign"]["1d"] < 0),
        "inst_buy": sum(1 for s in results if s["institution"]["1d"] > 0),
        "inst_sell": sum(1 for s in results if s["institution"]["1d"] < 0),
    }

    snapshot = {
        "date": date_iso,
        "signals": {"buy_reversal": [], "sell_reversal": [], "leader": [], "accumulation": []},
        "prices": prices,
        "foreign_1d": foreign_1d,
        "inst_1d": inst_1d,
        "pension_1d": pension_1d,
        "indi_1d": indi_1d,
        "corp_1d": corp_1d,
        "breadth": breadth,
        "market": {m.lower(): v["index"] for m, v in market_data.items()},
        "market_cap": market_cap,
        "trade_value": trade_value,
    }

    snap_dir = DATA_DIR / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    path = snap_dir / f"{date_iso}.json"
    path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    print(
        f"  snapshots/{date_iso}.json ({path.stat().st_size/1024:.1f} KB) "
        f"종가 {len(prices)} / 외국인 {len(foreign_1d)} / 기관 {len(inst_1d)} / "
        f"연기금 {len(pension_1d)} / 개인 {len(indi_1d)} / 기타법인 {len(corp_1d)}"
    )
    print(
        f"    breadth 외국인 +{breadth['foreign_buy']}/-{breadth['foreign_sell']} "
        f"기관 +{breadth['inst_buy']}/-{breadth['inst_sell']}"
    )

    # retention
    import re

    name_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    files = sorted(
        (f for f in snap_dir.glob("*.json") if name_re.match(f.stem)),
        key=lambda f: f.stem,
        reverse=True,
    )
    for old in files[MAX_SNAPSHOTS:]:
        old.unlink()
    if len(files) > MAX_SNAPSHOTS:
        print(f"    retention: {len(files) - MAX_SNAPSHOTS}개 삭제")


# ─── 메인 ───────────────────────────────────────────────────────────
def latest_business_day(kis):
    """KOSPI 지수가 조회되는 가장 최근 날짜를 기준일로 삼는다."""
    today = datetime.today().date()
    for _ in range(12):
        if today.weekday() >= 5:
            today -= timedelta(days=1)
            continue
        ymd = today.strftime("%Y%m%d")
        body = kis.get(
            "/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice",
            tr_id="FHKUP03500100",
            params={
                "FID_COND_MRKT_DIV_CODE": "U",
                "FID_INPUT_ISCD": "0001",
                "FID_INPUT_DATE_1": ymd,
                "FID_INPUT_DATE_2": ymd,
                "FID_PERIOD_DIV_CODE": "D",
            },
        )
        rows = body.get("output2") or []
        if isinstance(rows, dict):
            rows = [rows]
        rows = [r for r in rows if str(r.get("bstp_nmix_prpr", "")).strip()]
        if rows and rows[0].get("stck_bsop_date") == ymd:
            return ymd
        today -= timedelta(days=1)
    raise SystemExit("최근 영업일을 찾지 못했습니다.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="", help="기준일 YYYYMMDD (기본: 최근 영업일)")
    ap.add_argument("--depth", type=int, default=5,
                    help=f"종목당 수급 조회 횟수 (1회={ROWS_PER_CALL}영업일, 기본 5=150일). "
                         "6m(120영업일) 수익률은 기준일 포함 121행이 필요해 4로는 모자란다")
    ap.add_argument("--limit", type=int, default=0, help="상위 N 종목만 (테스트용)")
    ap.add_argument("--no-cache", action="store_true", help="캐시 무시")
    ap.add_argument("--skip-fundamentals", action="store_true",
                    help="PER/PBR/시총 조회 생략 (호출 절반 절약)")
    args = ap.parse_args()

    cache = not args.no_cache
    kis = KisClient()

    date_str = args.date or latest_business_day(kis)
    date_iso = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    print("=" * 60)
    print(f"KIS 전 종목 수집  기준일={date_iso}  depth={args.depth}")
    print("=" * 60)

    cb_state, cb_through = load_cost_basis()
    print(f"  기준가격 상태: {len(cb_state)}종목"
          + (f" (…{cb_through} 까지 반영됨)" if cb_through else "  (없음 — scripts/build_cost_basis.py 를 먼저 돌리면 정확해집니다)"))

    dividends = load_dividends()
    print(f"  배당 데이터: {len(dividends)}종목" + (
        "" if dividends
        else "  (없음 — scripts/kis_dividends.py 를 먼저 돌리면 배당수익률이 채워집니다)"))

    print("\n[1/4] 종목 유니버스 로드")
    universe = load_universe(args.limit or None)
    print(f"  총 {len(universe)}종목")

    print("\n[2/4] 시장 지수/자금흐름 수집")
    market_rows = fetch_market(kis, date_str)

    print(f"\n[3/4] 종목별 수급/시세 수집 (예상 {len(universe) * (args.depth + (0 if args.skip_fundamentals else 1)) / 6 / 60:.0f}분)")
    results = []
    failed = []
    ohlc_added = 0
    t0 = time.monotonic()

    for n, stock in enumerate(universe, 1):
        ticker = stock["ticker"]
        try:
            rows = fetch_history(kis, ticker, date_str, args.depth, cache)
        except KisError as e:
            failed.append((ticker, str(e)))
            continue

        if not rows or rows[-1]["stck_bsop_date"] != date_str:
            # 기준일 데이터가 없으면 거래정지/상장폐지 등. 건너뛴다.
            continue

        holdings_now = shares_now = 0
        foreign, institution, combined, inst_detail, pension, corp = aggregate_flows(rows)
        item = {
            "name": stock["name"],
            "market": stock["market"],
            "foreign": foreign,
            "institution": institution,
            "combined": combined,
            "ticker": ticker,
            "price_change": aggregate_price_changes(rows),
        }
        # 전 기간이 0 이면 필드 자체를 넣지 않는다
        if inst_detail:
            item["inst_detail"] = inst_detail
        if pension:
            item["pension"] = pension
        if corp:
            item["corp"] = corp

        # 스냅샷용 원시값
        last = rows[-1]
        item["_close"] = to_float(last.get("stck_clpr"))
        item["_trade_value"] = to_int(last.get("acml_tr_pbmn"))
        item["_foreign_1d"] = float(ntby_pbmn(last, "frgn"))
        item["_inst_1d"] = float(ntby_pbmn(last, "orgn"))
        item["_pension_1d"] = float(ntby_pbmn(last, "fund"))
        # 개인·기타법인. 같은 응답에 이미 들어있어서 추가 호출이 없다.
        #   개인    — 체결 타이밍 분해(어제↑오늘↓ 받아내기 등)에 필요
        #   기타법인 — 자사주 매입·계열사 지분·M&A 축적. 이 데이터에서
        #             내부자에 가장 가까운 매수 주체다.
        item["_indi_1d"] = float(ntby_pbmn(last, "prsn"))
        item["_corp_1d"] = float(ntby_pbmn(last, "etc_corp"))

        if not args.skip_fundamentals:
            try:
                f = fetch_fundamentals(kis, ticker, date_str, cache)
                holdings_now = to_int(f.get("frgn_hldn_qty"))
                shares_now = to_int(f.get("lstn_stcn"))
                item["per"] = to_float(f.get("per")) or None
                item["pbr"] = to_float(f.get("pbr")) or None
                item["eps"] = to_int(f.get("eps")) or None
                item["bps"] = to_int(f.get("bps")) or None
                # hts_avls 는 억원 단위 — 기존 스키마와 동일
                item["market_cap"] = to_float(f.get("hts_avls")) or None
                # KIS 현재가 시세에는 배당수익률이 없다.
                # kis_dividends.py 가 받아둔 주당배당금을 종가로 나눠 계산한다.
                # dividends.json 은 '액면가 1원당 배당액'이라 현재 액면가를 곱해
                # 현재 주식 기준 주당배당금으로 되돌린다 (기간 중 액면분할 보정).
                ratio = dividends.get(ticker)
                face = to_int(f.get("stck_fcam"))
                close = item["_close"]
                dps = ratio * face if ratio and face > 0 else 0
                item["div_yield"] = (
                    round(dps / close * 100, 2) if dps and close > 0 else None
                )
            except KisError as e:
                failed.append((ticker, f"fundamentals: {e}"))

        # 평균단가는 회전율 가중 기준가격으로 계산한다. 외국인 보유량이 필요해서
        # 재무 조회 뒤에 온다. 출력 스키마는 기존 avg_cost 그대로다.
        entry = update_cost_basis(
            cb_state.get(ticker), rows, holdings_now, shares_now, cb_through
        )
        if entry:
            cb_state[ticker] = entry
            avg = cost_basis_to_avg_cost(entry, item["_close"])
            if avg:
                item["avg_cost"] = avg

        basis = None
        if entry:
            close_now = item["_close"]
            fb = cb.summarize(entry.get("f"), close_now)
            ib = cb.summarize(entry.get("i"), close_now)
            basis = {"f": fb["basis"] if fb else None, "i": ib["basis"] if ib else None}
        ohlc_added += append_ohlc(ticker, rows, basis)

        results.append(item)

        if n % 100 == 0 or n == len(universe):
            el = time.monotonic() - t0
            rate = n / el if el else 0
            eta = (len(universe) - n) / rate / 60 if rate else 0
            print(f"  {n}/{len(universe)}  수집 {len(results)}  실패 {len(failed)}  "
                  f"경과 {el/60:.1f}분  남은시간 ~{eta:.0f}분")

    print(f"\n[4/4] 저장")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print(f"  ohlc/ ({ohlc_added}개 일봉 추가)")
    save_cost_basis(cb_state, date_iso)
    print(f"  cost-basis.json ({len(cb_state)}종목)")

    market_data = build_market_overview(market_rows, date_iso, date_str)
    build_kospi_history(market_rows, date_str)
    build_snapshot(results, market_data, date_iso)

    # 스냅샷 전용 원시값은 프론트로 내보낼 필요가 없어 여기서 떼어낸다
    for item in results:
        for k in ("_close", "_trade_value", "_foreign_1d", "_inst_1d", "_pension_1d"):
            item.pop(k, None)

    payload = {
        "date": date_iso,
        "unit": "백만원",
        "count": len(results),
        "data": results,
    }
    out_path = DATA_DIR / "stock-rankings.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"  stock-rankings.json ({out_path.stat().st_size/1024:.1f} KB, {len(results)}종목)")

    # 필드명을 바꾸면 안 된다. app/page.tsx:646-647 이 meta.business_date 와
    # meta.last_updated 를 직접 읽고, last_updated 에 .includes() 를 호출한다.
    # (한 번 date/updated_at 으로 바꿨다가 홈 전체가 TypeError 로 죽었다)
    now = datetime.now()
    hour = now.hour
    ampm = "오전" if hour < 12 else "오후"
    hour12 = hour if hour <= 12 else hour - 12
    meta_path = DATA_DIR / "meta.json"
    meta_path.write_text(
        json.dumps(
            {
                "last_updated": f"{ampm} {hour12 or 12}시 {now.minute:02d}분",
                "business_date": date_iso,
                "version": "2.0",
                "count": len(results),
                "source": "KIS Open API",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print("  meta.json")

    if failed:
        print(f"\n  실패 {len(failed)}건 (상위 5건):")
        for t, e in failed[:5]:
            print(f"    {t}: {e[:90]}")

    print(f"\n총 소요 {(time.monotonic()-t0)/60:.1f}분")
    return 0


if __name__ == "__main__":
    sys.exit(main())
