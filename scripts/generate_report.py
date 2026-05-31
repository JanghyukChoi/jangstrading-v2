"""
매일 수급 데이터 + 뉴스 본문 기반으로 AI 시황 분석 글을 자동 생성하는 스크립트

1. stock-rankings.json에서 핵심 수급 데이터 추출 (토큰 절약)
2. 네이버 금융 뉴스 최대 20건의 제목 + 본문 크롤링
   (n.news.naver.com/mnews/... 모바일 URL → #dic_area 셀렉터)
3. Claude Sonnet 4.6 API 호출 → 5섹션 구조 시황 글 생성
   (TL;DR / 핵심 숫자 / 구조적 해석 / 주목할 신호 / 종합 판단)
4. public/data/reports/YYYY-MM-DD.json 저장

실행: python scripts/generate_report.py
비용: 하루 약 $0.10~0.20 (Sonnet 4.6, 입력 ~20K + 출력 ~3~4K 토큰)
"""

import json
import os
import re
import time
import requests
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse, parse_qs
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "public" / "data"
REPORTS_DIR = DATA_DIR / "reports"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# 네이버 모바일 뉴스 본문 셀렉터 (검증 결과 #dic_area 단일로 100% 매칭)
BODY_SELECTORS = ["#dic_area", "#newsct_article", "._article_content", "._article_body_contents"]


def to_mobile_news_url(legacy_url: str):
    """
    finance.naver.com/news/news_read.naver?article_id=X&office_id=Y
    → n.news.naver.com/mnews/article/Y/X (실제 본문이 있는 모바일 URL)
    """
    parsed = urlparse(legacy_url)
    qs = parse_qs(parsed.query)
    article_id = qs.get("article_id", [None])[0]
    office_id = qs.get("office_id", [None])[0]
    if article_id and office_id:
        return f"https://n.news.naver.com/mnews/article/{office_id}/{article_id}"
    return None


def extract_article_body(html: str):
    """모바일 뉴스 HTML에서 본문 텍스트 추출"""
    soup = BeautifulSoup(html, "html.parser")
    for selector in BODY_SELECTORS:
        try:
            elem = soup.select_one(selector)
        except Exception:
            continue
        if elem:
            for tag in elem.select("script, style, iframe, .ad, .related, .copyright"):
                tag.decompose()
            text = elem.get_text(separator=" ", strip=True)
            text = re.sub(r"\s+", " ", text)
            if len(text) > 100:
                return text
    return None


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


def crawl_news(max_items: int = 20):
    """
    네이버 금융 뉴스 목록에서 기사 링크를 수집한 뒤,
    모바일 뉴스(n.news.naver.com)에서 본문까지 추출.
    반환: [{title, body, url}, ...] (본문 추출 실패 건은 제외)
    """
    list_urls = [
        "https://finance.naver.com/news/mainnews.naver",
        "https://finance.naver.com/news/news_list.naver?mode=LSS2D&section_id=101&section_id2=258",
    ]
    # 1) 기사 링크 수집
    articles = []
    seen = set()
    for list_url in list_urls:
        try:
            r = requests.get(list_url, headers=HEADERS, timeout=10)
            r.encoding = "euc-kr"
            soup = BeautifulSoup(r.content.decode("euc-kr", errors="replace"), "html.parser")
            for a in soup.select("dd.articleSubject a"):
                title = a.text.strip()
                href = a.get("href", "")
                if not title or len(title) <= 5 or not href:
                    continue
                if href.startswith("/"):
                    href = "https://finance.naver.com" + href
                elif not href.startswith("http"):
                    continue
                if href in seen:
                    continue
                seen.add(href)
                articles.append({"title": title, "url": href})
                if len(articles) >= max_items:
                    break
            if len(articles) >= max_items:
                break
        except Exception as e:
            print(f"  ⚠️ 뉴스 목록 크롤링 실패: {e}")

    # 2) 각 기사 본문 추출
    result = []
    for item in articles:
        time.sleep(0.3)  # 폴라이트 딜레이
        mobile_url = to_mobile_news_url(item["url"])
        if not mobile_url:
            continue
        try:
            r = requests.get(mobile_url, headers=HEADERS, timeout=10)
            if r.encoding == "ISO-8859-1":
                r.encoding = r.apparent_encoding or "utf-8"
            body = extract_article_body(r.text)
            if body:
                # 본문이 너무 길면 cap (토큰 절약, 핵심은 앞부분)
                result.append({
                    "title": item["title"],
                    "body": body[:1800],
                    "url": mobile_url,
                })
        except Exception as e:
            print(f"  ⚠️ 본문 추출 실패 ({item['title'][:30]}): {e}")
            continue

    return result


def generate_with_claude(date, data_summary, news_items):
    """Claude Sonnet 4.6 API로 시황 분석 글 생성 (제목+본문 뉴스 컨텍스트 활용)"""
    if not ANTHROPIC_API_KEY:
        print("  ❌ ANTHROPIC_API_KEY가 설정되지 않았습니다.")
        return None

    if news_items:
        news_blocks = []
        for i, n in enumerate(news_items, 1):
            news_blocks.append(f"[뉴스 {i}] {n['title']}\n{n['body']}")
        news_text = "\n\n".join(news_blocks)
    else:
        news_text = "(뉴스 없음)"

    prompt = f"""당신은 한국 증시 분석가입니다. 매일 KOSPI/KOSDAQ 수급 데이터와 뉴스 본문을 종합해 개인투자자용 시황 글을 작성합니다.

[수급 데이터]
{data_summary}

[오늘의 주요 뉴스 (제목 + 본문)]
{news_text}

# 본문 구조 (1,500~2,000자, 마크다운 없이 순수 텍스트)

## 1. 한 줄 요약 (TL;DR, 3~4문장)
오늘 시장의 핵심 흐름을 압축. 숫자 1~2개 포함.

## 2. 오늘의 핵심 숫자 (4~6개)
각 숫자에 비교 맥락 한 줄 부연.
예: "외국인 +5.2조원 (이번 주 누적 +12조, 6주 만에 최대)"
예: "[특정 섹터] 외인 매수세 +1,200억원 (3개월 만에 최대 유입)"
종목 예시를 들 때는 매일 다른 종목·섹터를 선택할 것.

## 3. 표면 데이터의 구조적 해석 (3~4개 포인트)
단순 paraphrase 금지. 다음 구조로:
- 데이터 → 왜 이런 흐름인가 (뉴스 본문에서 배경 추출) → 향후 함의
- 수급과 뉴스를 연결해 "왜 그 섹터/종목이 매수/매도됐는지" 분석
- TOP 10 종목만 보지 말고 섹터 TOP 5, 수급 신호, 외인·기관 동조 등 다양한 데이터를 활용

## 4. 가장 주목할 신호 1개
오늘 가장 의미있는 시그널 1개 (수급 전환, 섹터 쏠림, 특정 종목 이벤트 등).
정량 데이터 + 메커니즘(왜 이게 중요한지).
신고가/저가 종목, 매수전환·집중매수 발생 종목 등에서도 좋은 후보가 나올 수 있음.

## 5. 종합 판단 + 관전 포인트
오늘 시장을 한 문장으로 정의. 다음 영업일 관전 포인트 1~2개.

# 다양성 가이드 (매우 중요)
- **삼성전자·SK하이닉스 같은 메가캡 반도체에 글을 집중시키지 말 것**
- 두 종목은 시총이 커서 TOP 10에 자주 등장하지만, 그것만 다루면 매일 같은 글이 됨
- 매일 다른 섹터·종목이 글의 중심에 오도록 의식적으로 분산:
  - 화장품·식품·소비재, 자동차·부품, 2차전지·소재, 바이오·제약, 금융·증권,
    조선·기계, 미디어·엔터·게임, 건설·인프라, 통신·유틸리티, 방산 등
- 메가캡 반도체는 언급해도 좋지만 글의 1~2개 포인트로 제한
- 섹터 TOP 5 매수/매도 변화, 시그널 발생 종목, 외인·기관 의견 분열 같은 데이터를 적극 활용
- 매일 다른 "주인공"이 등장하도록 의식할 것

# 스타일 규칙
- 어미 다양화: "~다", "~이다" 3문장 연속 금지
- 의문문·짧은 단답형 문장 3개 이상 섞기
- 문장 길이 변화 (5단어 문장과 25단어 문장 교차)
- 1인칭(나/저) 사용 금지 — 사이트 분석가 톤 유지
- 추측은 "~할 가능성", "~로 보이는데" 같은 hedging 표현

# 금지 표현 (AI 흔적)
- "~로 풀이된다", "주목해야 한다", "주요한 신호로 볼 수 있다"
- "~점이 흥미롭다", "~에 다름 아니다", "~로 해석할 수 있다" (글 전체 1회만)
- "다음과 같은 의미를 갖는다", "유의하시기 바랍니다" 형식 문구

# 숫자 사용
- 모든 핵심 수치에 "맥락 한 줄" 부연 (전년 대비, 역대 최고, n개월 만 등)
- 숫자 단독 나열 금지

# 절대 금지
- 투자 추천 표현 ("매수하세요", "추천드립니다")
- 근거 없는 낙관/비관
- 모호한 표현 ("좋아 보인다", "긍정적일 수 있다")
- 교과서적 설명 ("ETF란~", "PER은~")
- 마크다운 헤더(##) — 순수 텍스트로 줄바꿈만 사용

# 출력 형식
다음 XML 태그 형식으로만 응답 (앞뒤 설명 X, 줄바꿈 자유롭게 사용 가능):

<title>제목 (40자 이내, 핵심 숫자 또는 키워드 1개 포함)</title>
<body>
본문 전체
줄바꿈 그대로 사용
</body>
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
                "model": "claude-sonnet-4-6",
                "max_tokens": 5000,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=120,
        )

        if r.status_code != 200:
            print(f"  ❌ API 오류: {r.status_code} {r.text[:200]}")
            return None

        response = r.json()
        text = response["content"][0]["text"]

        # XML 태그 추출 (<title>...</title>, <body>...</body>)
        title_match = re.search(r"<title>\s*(.+?)\s*</title>", text, re.DOTALL)
        body_match = re.search(r"<body>\s*([\s\S]+?)\s*</body>", text)

        if title_match and body_match:
            return {
                "title": title_match.group(1).strip(),
                "body": body_match.group(1).strip(),
            }

        # 태그 파싱 실패 — 응답 일부를 로그로 남기고 fallback
        print(f"  ⚠️ XML 태그 파싱 실패. 응답 첫 300자: {text[:300]}")
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

    # 2. 뉴스 크롤링 (제목 + 본문)
    news = crawl_news(max_items=20)
    if news:
        avg_body = sum(len(n["body"]) for n in news) // len(news)
        print(f"  📰 뉴스 본문 추출: {len(news)}건 (평균 {avg_body:,}자)")
    else:
        print(f"  📰 뉴스 본문 추출: 0건")

    # 3. Claude API 호출
    report = generate_with_claude(date, data_summary, news)
    if not report:
        print("  ❌ 리포트 생성 실패")
        return

    print(f"  ✅ 리포트 생성 완료: {report['title']}")

    # 4. 저장
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    from datetime import timezone, timedelta as td
    kst = timezone(td(hours=9))
    report_data = {
        "date": date,
        "title": report["title"],
        "body": report["body"],
        "generated_at": datetime.now(kst).strftime("%Y-%m-%d %H:%M KST"),
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
