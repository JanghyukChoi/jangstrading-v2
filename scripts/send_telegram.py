"""
텔레그램 채널에 일일 수급 시황 요약을 발송하는 스크립트

실행: python scripts/send_telegram.py
GitHub Actions에서 generate_report.py 이후에 실행

필요한 환경 변수:
  TELEGRAM_BOT_TOKEN: BotFather에서 받은 토큰
  TELEGRAM_CHANNEL_ID: 채널 username (예: @jangstrading)
"""

import html
import json
import os
import re
from pathlib import Path
import requests

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "public" / "data"

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "")
SITE_URL = "https://www.jangstrading.com"

TG_LIMIT = 3900  # 텔레그램 메시지 최대 4096자 — 여유 두고 분할


def send_message(text, parse_mode="HTML"):
    """텔레그램 채널에 메시지 1건 발송. 성공 여부 반환."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    resp = requests.post(url, json={
        "chat_id": CHANNEL_ID,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }, timeout=10)
    if resp.status_code == 200:
        print("✅ 텔레그램 발송 성공!")
        return True
    print(f"❌ 텔레그램 발송 실패: {resp.status_code} {resp.text}")
    return False


def send_ai_report():
    """generate_report.py가 만든 AI 시황 전문을 두 번째 메시지로 발송.
    4096자 제한 시 문단(\\n\\n) 단위로 나눠 발송."""
    try:
        with open(DATA_DIR / "reports" / "index.json", "r", encoding="utf-8") as f:
            idx = json.load(f)
        if not idx:
            print("  [INFO] 리포트 인덱스 비어있음 — AI 시황 발송 생략")
            return
        rdate = idx[0].get("date", "")
        with open(DATA_DIR / "reports" / f"{rdate}.json", "r", encoding="utf-8") as f:
            report = json.load(f)
    except Exception as e:
        print(f"  [WARN] AI 리포트 로드 실패 — 발송 생략: {e}")
        return

    title = report.get("title", "")
    body = report.get("body", "")
    if not body.strip():
        print("  [INFO] 리포트 본문 없음 — AI 시황 발송 생략")
        return

    def esc(s):
        return html.escape(s, quote=False)  # & < > 만 이스케이프

    # [섹션 제목] 줄을 볼드 처리 (이스케이프 후 태그 삽입)
    body_fmt = re.sub(r"(?m)^(\[[^\]\n]+\])\s*$", r"<b>\1</b>", esc(body))
    header = f"📝 <b>{esc(title)}</b>\n\n" if title else ""
    footer = f"\n\n👉 {SITE_URL}/reports/{rdate}"
    full = header + body_fmt + footer

    # 문단 단위로 TG_LIMIT 이하 묶음 발송
    messages, cur = [], ""
    for para in full.split("\n\n"):
        if cur and len(cur) + 2 + len(para) > TG_LIMIT:
            messages.append(cur)
            cur = para
        else:
            cur = f"{cur}\n\n{para}" if cur else para
    if cur:
        messages.append(cur)

    print(f"📨 AI 시황 발송 ({len(messages)}개 메시지, 총 {len(full)}자)")
    for m in messages:
        send_message(m)


def fmtUnit(n):
    """백만원 → 읽기 쉬운 형태"""
    won = n * 1_000_000
    abs_won = abs(won)
    sign = "+" if won > 0 else ""
    if abs_won >= 1e12:
        return f"{sign}{won / 1e12:.1f}조"
    if abs_won >= 1e8:
        return f"{sign}{round(won / 1e8):,}억"
    if abs_won >= 1e4:
        return f"{sign}{round(won / 1e4):,}만"
    return f"{sign}{round(won):,}원"


def main():
    if not BOT_TOKEN or not CHANNEL_ID:
        print("❌ TELEGRAM_BOT_TOKEN 또는 TELEGRAM_CHANNEL_ID가 설정되지 않았습니다.")
        return

    # 1. 데이터 로드
    with open(DATA_DIR / "stock-rankings.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    stocks = data["data"]
    date = data["date"]

    # 시장 개요
    market_data = None
    try:
        with open(DATA_DIR / "market-overview.json", "r", encoding="utf-8") as f:
            market_data = json.load(f)["data"]
    except Exception:
        pass

    # 2. 지수
    idx_line = ""
    if market_data:
        try:
            kospi = market_data.get("KOSPI", {})
            kosdaq = market_data.get("KOSDAQ", {})
            ki = kospi.get("index") if isinstance(kospi.get("index"), dict) else {"value": kospi.get("index", ""), "change_pct": kospi.get("change_pct", 0)}
            kd = kosdaq.get("index") if isinstance(kosdaq.get("index"), dict) else {"value": kosdaq.get("index", ""), "change_pct": kosdaq.get("change_pct", 0)}
            kv = ki.get("value", "")
            kc = ki.get("change_pct", 0)
            dv = kd.get("value", "")
            dc = kd.get("change_pct", 0)
            ks = f"+{kc}" if kc > 0 else str(kc)
            ds = f"+{dc}" if dc > 0 else str(dc)
            idx_line = f"KOSPI {kv} ({ks}%) | KOSDAQ {dv} ({ds}%)"
        except Exception:
            pass

    # 3. 수급 신호 카운트 — V3 signals.json (사이트와 동일)
    signals = {"buy": 0, "sell": 0, "leader": 0, "acc": 0, "ai": 0}
    try:
        with open(DATA_DIR / "signals.json", "r", encoding="utf-8") as f:
            v3 = json.load(f)
        s_dict = v3.get("signals") or {}
        signals["buy"] = len(s_dict.get("buy_reversal", []))
        signals["sell"] = len(s_dict.get("sell_reversal", []))
        signals["leader"] = len(s_dict.get("leader", []))
        signals["acc"] = len(s_dict.get("accumulation", []))
        signals["ai"] = len((v3.get("longterm") or {}).get("ai_screener", []))
    except Exception as e:
        print(f"  [WARN] signals.json 로드 실패: {e}")

    # 4. 섹터별 주도주 (중분류 TOP 3)
    sector_map = {}
    for s in stocks:
        mid = s.get("sector_mid", "기타")
        if mid == "기타":
            continue
        if mid not in sector_map:
            sector_map[mid] = {"total": 0, "stocks": []}
        flow = s["combined"].get("1m", 0)
        sector_map[mid]["total"] += flow
        mom = s.get("price_change", {}).get("1m", 0) or 0
        sector_map[mid]["stocks"].append({"name": s["name"], "flow": flow, "mom": mom, "ticker": s.get("ticker", "")})

    top_sectors = sorted(sector_map.items(), key=lambda x: x[1]["total"], reverse=True)[:3]

    # 각 섹터 내 주도주 (CLS 간이 계산 → 상위 3개)
    leader_lines = []
    for sec_name, sec_data in top_sectors:
        total_pos = sum(max(s["flow"], 0) for s in sec_data["stocks"])
        all_mom = [s["mom"] for s in sec_data["stocks"]]

        def pct_rank(vals, v):
            below = sum(1 for x in vals if x < v)
            return below / max(len(vals) - 1, 1) * 100

        scored = []
        for s in sec_data["stocks"]:
            if s["flow"] <= 0:
                continue
            share = (s["flow"] / total_pos * 100) if total_pos > 0 else 0
            n_mom = pct_rank(all_mom, s["mom"])
            cls = 0.35 * n_mom + 0.25 * min(share * 5, 100)
            scored.append((s, cls))

        scored.sort(key=lambda x: x[1], reverse=True)
        leaders = [s[0] for s in scored[:3]]
        leader_names = ", ".join(s["name"] for s in leaders)
        leader_lines.append(f"{sec_name} {fmtUnit(sec_data['total'])}\n→ {leader_names}")

    # 5. 외국인 / 기관 순매수 TOP3
    foreign_top = sorted(stocks, key=lambda x: x["foreign"].get("1m", 0), reverse=True)[:3]
    inst_top = sorted(stocks, key=lambda x: x["institution"].get("1m", 0), reverse=True)[:3]

    foreign_lines = []
    for i, s in enumerate(foreign_top):
        foreign_lines.append(f"{i+1}. {s['name']} {fmtUnit(s['foreign']['1m'])}")

    inst_lines = []
    for i, s in enumerate(inst_top):
        inst_lines.append(f"{i+1}. {s['name']} {fmtUnit(s['institution']['1m'])}")

    # 6. AI 시황 제목
    report_title = ""
    try:
        with open(DATA_DIR / "reports" / "index.json", "r", encoding="utf-8") as f:
            idx = json.load(f)
            if idx:
                report_title = idx[0].get("title", "")
    except Exception:
        pass

    # 7. 메시지 조립
    msg = f"📊 {date} 수급 시황\n\n"

    if idx_line:
        msg += f"{idx_line}\n\n"

    msg += f"🔥 수급 신호 (시총가중 V3)\n"
    msg += f"매수전환 {signals['buy']} | 매도전환 {signals['sell']} | 주도주 {signals['leader']}\n"
    msg += f"단기수급상위 {signals['acc']} | 장기수급상위 {signals['ai']}\n\n"

    msg += "⭐ 섹터별 주도주 (1개월)\n"
    msg += "\n".join(leader_lines)
    msg += "\n\n"

    msg += "💰 외국인 순매수 TOP3\n"
    msg += "\n".join(foreign_lines)
    msg += "\n\n"

    msg += "🏦 기관 순매수 TOP3\n"
    msg += "\n".join(inst_lines)
    msg += "\n\n"

    if report_title:
        msg += f"📝 {report_title}\n\n"

    msg += f"👉 {SITE_URL}"

    print("📨 텔레그램 발송 메시지:")
    print(msg)
    print()

    # 8. 발송 — ① 수급 시황 요약
    send_message(msg)

    # ② AI 시황 전문 (요약 메시지 다음에 이어서 발송)
    send_ai_report()


if __name__ == "__main__":
    main()
