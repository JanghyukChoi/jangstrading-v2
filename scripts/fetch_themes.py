"""
네이버 금융 테마 데이터를 크롤링하여 theme-map.json으로 저장
테마명 → 구성종목(티커) 매핑

실행: python scripts/fetch_themes.py
소요: 약 3분 (312개 테마 × 0.5초)
"""

import json
import re
import time
import requests
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "public" / "data"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def fetch_theme_list():
    """전체 테마 목록 수집 (테마번호, 테마명)"""
    themes = {}  # no -> name (중복 제거)
    for page in range(1, 15):
        try:
            r = requests.get(
                f"https://finance.naver.com/sise/theme.naver?page={page}",
                headers=HEADERS,
                timeout=10,
            )
            r.encoding = "euc-kr"
            text = r.content.decode("euc-kr", errors="replace")

            matches = re.findall(r'type=theme&no=(\d+)"[^>]*>\s*([^<]+)', text)
            if not matches:
                break

            for no, name in matches:
                themes[no] = name.strip()

            print(f"  페이지 {page}: {len(matches)}개 테마")
            time.sleep(0.3)
        except Exception as e:
            print(f"  ❌ 페이지 {page} 실패: {e}")
            break

    return themes


def fetch_theme_stocks(theme_no):
    """특정 테마의 구성종목 티커 목록을 가져온다"""
    try:
        r = requests.get(
            f"https://finance.naver.com/sise/sise_group_detail.naver?type=theme&no={theme_no}",
            headers=HEADERS,
            timeout=10,
        )
        r.encoding = "euc-kr"
        text = r.content.decode("euc-kr", errors="replace")

        codes = re.findall(r"main\.naver\?code=(\d{6})", text)
        return list(set(codes))
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
    with open(theme_path, "w", encoding="utf-8") as f:
        json.dump(theme_map, f, ensure_ascii=False)

    size_kb = theme_path.stat().st_size / 1024
    print(f"✅ theme-map.json 저장 완료 ({size_kb:.1f} KB)")

    # 통계
    total_stocks = sum(len(v) for v in theme_map.values())
    avg = total_stocks / len(theme_map) if theme_map else 0
    print(f"📊 테마당 평균 {avg:.1f}개 종목, 총 {total_stocks}개 매핑")


if __name__ == "__main__":
    main()
