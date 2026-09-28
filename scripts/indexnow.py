"""
IndexNow — 데이터가 갱신되면 검색엔진에 **즉시 알린다**.

왜 필요한가
  사이트맵은 수동적이다. 크롤러가 올 때까지 기다린다. 네이버는 26.05.24 에
  사이트맵을 받아갔지만 4개월간 유입이 사실상 0이었다. 구글 쪽도 색인된
  657 페이지가 사이트맵 2,958 개에 한참 못 미친다.

  IndexNow 는 반대 방향이다. 우리가 "이 URL 들이 방금 바뀌었다"고 밀어 넣는다.
  네이버가 23.07.25 부터 지원하고(서치어드바이저 공지), Bing·Yandex·Seznam 도
  같은 프로토콜을 쓴다. 무료이고 인증은 도메인 루트의 키 파일로 한다.

무엇을 보낼 것인가 — 여기가 핵심이다
  프로토콜 규약상 **실제로 바뀐 URL 만** 보내야 한다. 안 바뀐 URL 을 매일
  밀어 넣으면 스팸으로 취급되어 도메인 신뢰도가 깎인다.

  이 사이트는 기술적으로는 2,600 종목이 매일 다 바뀐다. 그렇다고 매일 2,600 개를
  밀면 "전량 재제출"로 보여 위 규약에 걸린다. 그래서 두 가지를 섞는다.

    고정        홈·목록·가이드 등 진입점 + 그날 생성된 리포트
    변화량 상위 그날 수급이 실제로 크게 움직인 종목 (TOP_N)
    순환        전체 종목을 날짜로 나눈 조각 (ROTATE_N)

  순환이 있어야 거래가 적어 변화량 상위에 영원히 못 드는 종목도 색인된다.
  2,600 종목 / 하루 120 개면 약 3주에 한 바퀴다.

키 파일
  public/<KEY>.txt 에 키 문자열만 들어 있다. Next 가 public/ 을 루트로
  서빙하므로 https://www.jangstrading.com/<KEY>.txt 로 노출된다.
  이 파일이 없거나 내용이 다르면 제출이 통째로 거부된다.

실행
  python scripts/indexnow.py              # 제출
  python scripts/indexnow.py --dry-run    # 보낼 URL 만 출력
"""

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

# 윈도우 콘솔 기본 코덱이 cp949 라 한글·em dash 출력에서 죽는다. CI(리눅스)는
# UTF-8 이라 문제없지만 로컬에서 돌려볼 수 있어야 한다.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "public" / "data"

HOST = "www.jangstrading.com"
ORIGIN = f"https://{HOST}"
KEY = "2b707d08b8225b68c1609d3fa0f61c11"
KEY_FILE = BASE / "public" / f"{KEY}.txt"

# 네이버는 자체 엔드포인트를 쓴다. api.indexnow.org 는 Bing·Yandex·Seznam 으로
# 전파된다. 둘 다 보낸다 — 한쪽이 죽어도 다른 쪽은 간다.
ENDPOINTS = [
    ("naver", "https://searchadvisor.naver.com/indexnow"),
    ("indexnow", "https://api.indexnow.org/indexnow"),
]

TOP_N = 80        # 그날 수급 변화가 큰 종목
ROTATE_N = 120    # 순환 조각 크기

FIXED = ["/", "/stocks", "/sectors", "/screener", "/reports", "/guide/평균단가"]


def enc(path):
    """한글 경로를 퍼센트 인코딩한다. /guide/평균단가, /sectors/건강관리 등.

    IndexNow 는 URL 을 문자 그대로 비교하므로 인코딩이 틀리면 조용히 버려진다.
    """
    return ORIGIN + urllib.parse.quote(path, safe="/")


def load_json(name):
    try:
        return json.loads((DATA / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def build_urls():
    urls = [enc(p) for p in FIXED]

    rankings = load_json("stock-rankings.json") or {}
    rows = [s for s in rankings.get("data", []) if s.get("ticker")]
    data_date = rankings.get("date", "")

    # 그날 리포트. 없으면 건너뛴다(Gemini 실패한 날).
    if data_date and (DATA / "reports" / f"{data_date}.json").exists():
        urls.append(enc(f"/reports/{data_date}"))

    if not rows:
        return urls

    def move(s):
        """그날 수급이 얼마나 움직였나. 1일 외국인+기관 절대금액."""
        f = abs((s.get("foreign") or {}).get("1d") or 0)
        i = abs((s.get("institution") or {}).get("1d") or 0)
        return f + i

    # 섹터 — /sectors/[name] 은 sector_mid(중분류)와 sector(대분류) 양쪽으로
    # 열린다. sector-rankings.json 은 비어 있어서 쓸 수 없다(data: []).
    # sitemap.ts 와 같은 방식으로 종목에서 직접 집계한다.
    sector_move = {}
    for s in rows:
        for key in (s.get("sector_mid"), s.get("sector")):
            if key and key != "기타":
                sector_move[key] = sector_move.get(key, 0) + move(s)
    hot = sorted(sector_move, key=sector_move.get, reverse=True)[:20]
    urls.extend(enc(f"/sectors/{n}") for n in hot)

    top = sorted(rows, key=move, reverse=True)[:TOP_N]
    picked = {s["ticker"] for s in top}

    # 순환 조각 — 티커 정렬 후 날짜로 오프셋. 거래가 적어 상위에 영원히 못 드는
    # 종목도 결국 한 바퀴 돈다.
    all_tickers = sorted(s["ticker"] for s in rows)
    if all_tickers:
        slots = max(1, -(-len(all_tickers) // ROTATE_N))
        start = (date.today().toordinal() % slots) * ROTATE_N
        picked.update(all_tickers[start:start + ROTATE_N])

    urls.extend(enc(f"/stocks/{t}") for t in sorted(picked))
    return urls


def submit(name, endpoint, urls):
    payload = json.dumps({
        "host": HOST,
        "key": KEY,
        "keyLocation": f"{ORIGIN}/{KEY}.txt",
        "urlList": urls,
    }).encode("utf-8")

    req = urllib.request.Request(
        endpoint, data=payload, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"  {name:9s} HTTP {r.status} — {len(urls)}개 제출")
            return True
    except urllib.error.HTTPError as e:
        # 200/202 외에 의미 있는 코드들: 400 형식오류, 403 키 불일치,
        # 422 host 불일치, 429 과다요청.
        body = e.read().decode("utf-8", "replace")[:200]
        print(f"  {name:9s} HTTP {e.code} — {body}")
        return False
    except (urllib.error.URLError, OSError) as e:
        print(f"  {name:9s} 실패 — {e}")
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not KEY_FILE.exists() or KEY_FILE.read_text(encoding="utf-8").strip() != KEY:
        print(f"키 파일이 없거나 내용이 다릅니다: {KEY_FILE}")
        print("  이게 맞지 않으면 제출이 통째로 거부됩니다.")
        return 1

    urls = build_urls()
    print(f"IndexNow — {len(urls)}개 URL")
    if args.dry_run:
        for u in urls:
            print(" ", urllib.parse.unquote(u))
        return 0

    ok = [submit(n, e, urls) for n, e in ENDPOINTS]
    # 한 곳이라도 성공하면 성공으로 본다. 색인 요청은 실패해도 데이터
    # 파이프라인을 막을 이유가 없다.
    return 0 if any(ok) else 1


if __name__ == "__main__":
    sys.exit(main())
