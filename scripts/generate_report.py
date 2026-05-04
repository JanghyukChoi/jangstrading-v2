"""
매일 수급 데이터 + 뉴스 기반으로 AI 시황 분석 글을 자동 생성하는 스크립트

1. stock-rankings.json에서 핵심 수급 데이터 추출 (토큰 절약)
2. 네이버 증권 뉴스 헤드라인 크롤링
3. Claude Haiku API 호출 → 시황 글 생성
4. public/data/reports/YYYY-MM-DD.json 저장

실행: python scripts/generate_report.py
비용: 하루 약 $0.01~0.02 (Haiku)
"""

import json
import os
import re
import requests
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "public" / "data"
REPORTS_DIR = DATA_DIR / "reports"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def extract_key_data():
    """stock-rankings.json에서 핵심 데이터만 추출 (토큰 절약)"""
    rankings_path = DATA_DIR / "stock-rankings.json"
    with open(rankings_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    stocks = data["data"]
    date = data["date"]

    # 1. 외국인 vs 기관 방향 일치
    big_stocks = [s for s in stocks if (s.get("market_cap") or 0) >= 1000]
    both_buy = sum(1 for s in big_stocks if s["foreign"].get("1m", 0) > 0 and s["institution"].get("1m", 0) > 0)
    both_sell = sum(1 for s in big_stocks if s["foreign"].get("1m", 0) < 0 and s["institution"].get("1m", 0) < 0)
    mixed = len(big_stocks) - both_buy - both_sell

    # 2. 수급 집중도 (외국인)
    foreign_buyers = sorted(
        [s for s in stocks if s["foreign"].get("1m", 0) > 0],
        key=lambda x: x["foreign"]["1m"], reverse=True
    )
    foreign_total = sum(s["foreign"]["1m"] for s in foreign_buyers)
    foreign_top5 = foreign_buyers[:5]
    foreign_top5_sum = sum(s["foreign"]["1m"] for s in foreign_top5)
    foreign_concentration = round(foreign_top5_sum / foreign_total * 100, 1) if foreign_total > 0 else 0

    # 3. 수급 집중도 (기관)
    inst_buyers = sorted(
        [s for s in stocks if s["institution"].get("1m", 0) > 0],
        key=lambda x: x["institution"]["1m"], reverse=True
    )
    inst_total = sum(s["institution"]["1m"] for s in inst_buyers)
    inst_top5 = inst_buyers[:5]
    inst_top5_sum = sum(s["institution"]["1m"] for s in inst_top5)
    inst_concentration = round(inst_top5_sum / inst_total * 100, 1) if inst_total > 0 else 0

    # 4. 섹터별 수급 (중분류 기준 TOP 5 순매수/순매도)
    sector_map = {}
    for s in stocks:
        mid = s.get("sector_mid", s.get("sector", "기타"))
        if mid == "기타":
            continue
        if mid not in sector_map:
            sector_map[mid] = {"foreign": 0, "institution": 0, "combined": 0}
        sector_map[mid]["foreign"] += s["foreign"].get("1m", 0)
        sector_map[mid]["institution"] += s["institution"].get("1m", 0)
        sector_map[mid]["combined"] += s["combined"].get("1m", 0)

    sector_sorted = sorted(sector_map.items(), key=lambda x: x[1]["combined"], reverse=True)
    sector_top5_buy = sector_sorted[:5]
    sector_top5_sell = sector_sorted[-5:][::-1]

    # 5. 수급 신호 카운트
    signals = {"buy_reversal": 0, "sell_reversal": 0, "divergence": 0, "accumulation": 0}
    for s in big_stocks:
        c = s["combined"]
        pc = s.get("price_change", {})
        if c.get("3m", 0) < -5000 and c.get("1w", 0) > 500:
            signals["buy_reversal"] += 1
        if c.get("3m", 0) > 5000 and c.get("1w", 0) < -500:
            signals["sell_reversal"] += 1
        if c.get("1m", 0) > 5000 and (pc.get("1m", 0) or 0) < -5:
            signals["divergence"] += 1
        if c.get("1d", 0) > 50 and c.get("1w", 0) > 500 and c.get("1m", 0) > 5000:
            signals["accumulation"] += 1

    # 6. 주요 종목 TOP 10 (합산 순매수 기준)
    top_buy = sorted(stocks, key=lambda x: x["combined"].get("1m", 0), reverse=True)[:10]
    top_sell = sorted(stocks, key=lambda x: x["combined"].get("1m", 0))[:5]

    def fmt(n):
        """백만원 → 읽기 쉬운 형태"""
        won = n * 1_000_000
        if abs(won) >= 1e12:
            return f"{won/1e12:+.1f}조원"
        if abs(won) >= 1e8:
            return f"{won/1e8:+,.0f}억원"
        return f"{won:+,.0f}원"

    # 요약 텍스트 생성
    summary = f"""[기준일: {date}]

[외국인 vs 기관 방향 일치 (1개월, 시총 1천억 이상)]
동시 순매수: {both_buy}종목 / 엇갈림: {mixed}종목 / 동시 순매도: {both_sell}종목

[수급 집중도 (1개월)]
외국인: {foreign_concentration}% (상위 5종목이 전체 순매수의 {foreign_concentration}% 차지)
  {', '.join(f'{s["name"]} {fmt(s["foreign"]["1m"])}' for s in foreign_top5)}
기관: {inst_concentration}% (상위 5종목이 전체 순매수의 {inst_concentration}% 차지)
  {', '.join(f'{s["name"]} {fmt(s["institution"]["1m"])}' for s in inst_top5)}

[섹터 TOP5 순매수 (1개월, 중분류)]
{chr(10).join(f'  {i+1}. {name}: 외국인 {fmt(d["foreign"])}, 기관 {fmt(d["institution"])}, 합계 {fmt(d["combined"])}' for i, (name, d) in enumerate(sector_top5_buy))}

[섹터 TOP5 순매도 (1개월, 중분류)]
{chr(10).join(f'  {i+1}. {name}: 합계 {fmt(d["combined"])}' for i, (name, d) in enumerate(sector_top5_sell))}

[수급 신호 (시총 1천억 이상)]
매수전환: {signals["buy_reversal"]}종목 / 매도전환: {signals["sell_reversal"]}종목 / 수급·주가 괴리: {signals["divergence"]}종목 / 집중매수: {signals["accumulation"]}종목

[TOP 10 순매수 종목 (1개월)]
{chr(10).join(f'  {i+1}. {s["name"]}: 외국인 {fmt(s["foreign"]["1m"])}, 기관 {fmt(s["institution"]["1m"])}, 합계 {fmt(s["combined"]["1m"])}, 주가변동 {s.get("price_change",{}).get("1m","N/A")}%' for i, s in enumerate(top_buy))}

[TOP 5 순매도 종목 (1개월)]
{chr(10).join(f'  {i+1}. {s["name"]}: 합계 {fmt(s["combined"]["1m"])}' for i, s in enumerate(top_sell))}
"""
    return date, summary


def crawl_news():
    """네이버 증권 뉴스 헤드라인 크롤링"""
    headlines = []

    try:
        # 메인 뉴스
        r = requests.get(
            "https://finance.naver.com/news/mainnews.naver",
            headers=HEADERS, timeout=10
        )
        r.encoding = "euc-kr"
        soup = BeautifulSoup(r.content.decode("euc-kr", errors="replace"), "html.parser")

        for a in soup.select("dd.articleSubject a"):
            title = a.text.strip()
            if title and len(title) > 5:
                headlines.append(title)

        # 시장 뉴스도 추가
        r2 = requests.get(
            "https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258",
            headers=HEADERS, timeout=10
        )
        r2.encoding = "euc-kr"
        soup2 = BeautifulSoup(r2.content.decode("euc-kr", errors="replace"), "html.parser")

        for a in soup2.select("dd.articleSubject a"):
            title = a.text.strip()
            if title and len(title) > 5 and title not in headlines:
                headlines.append(title)

    except Exception as e:
        print(f"  ⚠️ 뉴스 크롤링 실패: {e}")

    # 최대 15개만
    return headlines[:20]


def generate_with_claude(date, data_summary, news_headlines):
    """Claude Haiku API로 시황 글 생성"""
    if not ANTHROPIC_API_KEY:
        print("  ❌ ANTHROPIC_API_KEY가 설정되지 않았습니다.")
        return None

    news_text = "\n".join(f"  - {h}" for h in news_headlines) if news_headlines else "  (뉴스 없음)"

    prompt = f"""당신은 한국 증시 전문 애널리스트입니다. 아래 데이터를 바탕으로 오늘의 증시 시황 분석 글을 작성해주세요.

{data_summary}

[오늘의 주요 뉴스 헤드라인]
{news_text}

## 작성 규칙:
1. 전문적이지만 개인투자자가 이해하기 쉽게 작성
2. 핵심 흐름을 먼저 요약하고, 세부 분석으로 들어감
3. 수급 데이터와 뉴스를 연결하여 인사이트 제공
4. "왜 이런 수급이 나왔는지" 배경 분석
5. 주의할 점이나 리스크도 언급
6. 총 800~1200자 분량
7. 마크다운 없이 순수 텍스트로 작성
8. 투자 추천이 아닌 분석임을 명시

## 구조:
- 제목 (한 줄)
- 시장 개요 (2~3줄)
- 외국인·기관 수급 핵심 (3~4줄)
- 주목할 섹터 (3~4줄)
- 주목할 종목 (3~4줄)
- 수급 신호 해석 (2~3줄)
- 종합 판단 및 유의점 (2~3줄)

JSON 형식으로 응답해주세요:
{{"title": "제목", "body": "본문 전체"}}
"""

    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 2000,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60,
        )

        if r.status_code != 200:
            print(f"  ❌ API 오류: {r.status_code} {r.text[:200]}")
            return None

        response = r.json()
        text = response["content"][0]["text"]

        # JSON 파싱
        # ```json ... ``` 형태 처리
        text = re.sub(r"```json\s*", "", text)
        text = re.sub(r"```\s*", "", text)
        result = json.loads(text.strip())
        return result

    except json.JSONDecodeError:
        print(f"  ⚠️ JSON 파싱 실패, 텍스트 그대로 저장")
        return {"title": f"{date} 증시 시황", "body": text}
    except Exception as e:
        print(f"  ❌ API 호출 실패: {e}")
        return None


def main():
    print("📝 일일 시황 리포트 생성 시작...")

    # 1. 핵심 데이터 추출
    date, data_summary = extract_key_data()
    print(f"  📅 기준일: {date}")
    print(f"  📊 데이터 요약: {len(data_summary)}자")

    # 2. 뉴스 크롤링
    news = crawl_news()
    print(f"  📰 뉴스 헤드라인: {len(news)}개")

    # 3. Claude API 호출
    report = generate_with_claude(date, data_summary, news)
    if not report:
        print("  ❌ 리포트 생성 실패")
        return

    print(f"  ✅ 리포트 생성 완료: {report['title']}")

    # 4. 저장
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_data = {
        "date": date,
        "title": report["title"],
        "body": report["body"],
        "generated_at": datetime.now().isoformat(),
        "news_count": len(news),
    }

    # 개별 파일
    report_path = REPORTS_DIR / f"{date}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)

    # 인덱스 파일 (목록용) — 최근 90일만 유지
    index_path = REPORTS_DIR / "index.json"
    if index_path.exists():
        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)
    else:
        index = []

    # 중복 방지
    index = [r for r in index if r["date"] != date]
    index.insert(0, {"date": date, "title": report["title"]})
    index = index[:365 * 10]  # 사실상 무제한

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    print(f"  ✅ {report_path} 저장 완료")
    print(f"  ✅ 인덱스: {len(index)}개 리포트")


if __name__ == "__main__":
    main()
