"""
네이버 금융 테마 데이터를 크롤링하여 theme-map.json으로 저장
테마명 → 구성종목(티커) 매핑

실행: python scripts/fetch_themes.py
소요: 약 2분 (266개 테마 × 0.3초)
"""

import json
import sys
import re
import time
import requests
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "public" / "data"

# 네이버 금융이 SPA(Npay 증권)로 개편되면서 finance.naver.com HTML 스크래핑이
# 죽었다(테마 링크 0개). 모바일 앱이 쓰는 JSON API 로 옮겼다.
API_BASE = "https://m.stock.naver.com/api"
API_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    ),
    "Referer": "https://m.stock.naver.com/",
    "Accept": "application/json",
}
PAGE_SIZE = 100

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def fetch_theme_list():
    """전체 테마 목록 수집 (테마번호, 테마명)

    네이버 금융이 SPA(Npay 증권)로 개편되면서 finance.naver.com HTML 스크래핑이
    죽었다. 모바일 앱이 쓰는 JSON API 로 옮겼다.
    """
    themes = {}  # no -> name (중복 제거)
    page = 1
    while page <= 30:
        try:
            r = requests.get(
                f"{API_BASE}/stocks/theme",
                params={"page": page, "pageSize": PAGE_SIZE},
                headers=API_HEADERS,
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"  ❌ 페이지 {page} 실패: {e}")
            break

        groups = data.get("groups") or []
        if not groups:
            break

        for g in groups:
            no, name = g.get("no"), (g.get("name") or "").strip()
            if no and name:
                themes[str(no)] = name

        total = data.get("totalCount", 0)
        print(f"  페이지 {page}: {len(groups)}개 (누적 {len(themes)}/{total})")
        if len(themes) >= total:
            break
        page += 1
        time.sleep(0.2)

    return themes


def fetch_theme_stocks(theme_no):
    """특정 테마의 구성종목 티커 목록을 가져온다"""
    try:
        r = requests.get(
            f"{API_BASE}/stocks/theme/{theme_no}",
            params={"page": 1, "pageSize": PAGE_SIZE},
            headers=API_HEADERS,
            timeout=15,
        )
        r.raise_for_status()
        stocks = r.json().get("stocks") or []
        return sorted({s["itemCode"] for s in stocks if s.get("itemCode")})
    except Exception:
        return []


def main():
    print("📊 네이버 테마 데이터 수집 시작...")

    # 1. 테마 목록 수집
    themes = fetch_theme_list()
    print(f"\n📋 총 {len(themes)}개 테마 발견\n")

    # 2. 각 테마의 구성종목 수집
    theme_map = {}
    done = 0
    for no, name in themes.items():
        stocks = fetch_theme_stocks(no)
        if stocks:
            theme_map[name] = stocks
        done += 1
        if done % 50 == 0:
            print(f"  ... {done}/{len(themes)} 완료")
        time.sleep(0.5)

    print(f"\n✅ {len(theme_map)}개 테마 수집 완료")

    # 3. 저장
    theme_path = DATA_DIR / "theme-map.json"

    # 수집이 실패했는데 그대로 쓰면 멀쩡하던 테마 데이터가 빈 파일로 날아간다.
    # 네이버 금융이 SPA(Npay 증권)로 개편되면서 실제로 0개가 나오는 중이라
    # 기존 파일을 지키고 실패로 끝낸다.
    if not theme_map:
        print("❌ 수집된 테마가 0개입니다. 기존 theme-map.json 을 보존합니다.")
        if theme_path.exists():
            prev = json.loads(theme_path.read_text(encoding="utf-8"))
            print(f"   (기존 {len(prev)}개 테마 유지)")
        return 1

    with open(theme_path, "w", encoding="utf-8") as f:
        json.dump(theme_map, f, ensure_ascii=False)

    size_kb = theme_path.stat().st_size / 1024
    print(f"✅ theme-map.json 저장 완료 ({size_kb:.1f} KB)")

    # 통계
    total_stocks = sum(len(v) for v in theme_map.values())
    avg = total_stocks / len(theme_map) if theme_map else 0
    print(f"📊 테마당 평균 {avg:.1f}개 종목, 총 {total_stocks}개 매핑")
    return 0


if __name__ == "__main__":
    sys.exit(main())
