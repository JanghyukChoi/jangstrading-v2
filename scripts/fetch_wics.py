"""
WICS 업종분류 데이터를 wiseindex.com에서 자동 수집하는 스크립트
대분류(10개) + 중분류(25개)를 가져와서 sector-map.json으로 저장

실행: python scripts/fetch_wics.py
"""

import json
import time
import requests
from pathlib import Path
from datetime import datetime, timedelta

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "public" / "data"

MID_SECTORS = {
    "G1010": ("에너지", "에너지"),
    "G1510": ("소재", "소재"),
    "G2010": ("산업재", "자본재"),
    "G2020": ("산업재", "상업서비스와공급품"),
    "G2030": ("산업재", "운송"),
    "G2510": ("경기관련소비재", "자동차와부품"),
    "G2520": ("경기관련소비재", "내구소비재와의류"),
    "G2530": ("경기관련소비재", "소비자서비스"),
    "G2550": ("경기관련소비재", "소매(유통)"),
    "G3010": ("필수소비재", "식품과기본식료품소매"),
    "G3020": ("필수소비재", "식품·음료·담배"),
    "G3030": ("필수소비재", "가정용품과개인용품"),
    "G3510": ("건강관리", "건강관리장비와서비스"),
    "G3520": ("건강관리", "제약과생물공학"),
    "G4010": ("금융", "은행"),
    "G4020": ("금융", "증권"),
    "G4030": ("금융", "다각화된금융"),
    "G4040": ("금융", "보험"),
    "G4510": ("IT", "소프트웨어와서비스"),
    "G4520": ("IT", "기술하드웨어와장비"),
    "G4530": ("IT", "반도체와반도체장비"),
    "G5010": ("커뮤니케이션서비스", "전기통신서비스"),
    "G5020": ("커뮤니케이션서비스", "미디어와엔터테인먼트"),
    "G5510": ("유틸리티", "유틸리티"),
}

BASE_URL = "https://www.wiseindex.com/Index/GetIndexComponets"


def get_dates_to_try():
    """stock-rankings.json 기준일 + 이전 영업일 5개를 시도 목록으로 반환"""
    dates = []

    # stock-rankings.json에서 기준일
    rankings_path = DATA_DIR / "stock-rankings.json"
    if rankings_path.exists():
        with open(rankings_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        base_date = data["date"].replace("-", "")
        dates.append(base_date)

    # 오늘부터 7일 뒤로 영업일 찾기
    today = datetime.today()
    for i in range(10):
        d = today - timedelta(days=i)
        if d.weekday() < 5:
            ds = d.strftime("%Y%m%d")
            if ds not in dates:
                dates.append(ds)
        if len(dates) >= 6:
            break

    return dates


def fetch_sector_stocks(sec_cd, date, retries=3):
    """특정 섹터 코드의 구성종목을 가져온다. 빈 응답·실패 시 재시도."""
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.get(
                BASE_URL,
                params={"ceil_yn": 0, "dt": date, "sec_cd": sec_cd},
                timeout=15,
            )
            if r.status_code == 200:
                data = r.json()
                lst = data.get("list", [])
                if lst:
                    return lst
                last_err = "empty list"
            else:
                last_err = f"HTTP {r.status_code}"
        except Exception as e:
            last_err = str(e)
        if attempt < retries - 1:
            time.sleep(1.0 * (attempt + 1))  # 1s, 2s 백오프
    return []


def main():
    dates_to_try = get_dates_to_try()
    print(f"📅 시도할 날짜: {dates_to_try}")

    # 첫 번째 섹터로 날짜 테스트
    working_date = None
    for date in dates_to_try:
        test = fetch_sector_stocks("G4530", date)  # 반도체 섹터로 테스트
        if len(test) > 0:
            working_date = date
            print(f"📅 유효한 날짜 발견: {working_date} ({len(test)}종목)")
            break
        print(f"  ⚠️ {date}: 데이터 없음, 이전 날짜 시도...")
        time.sleep(0.3)

    if not working_date:
        print("❌ 유효한 날짜를 찾을 수 없습니다.")
        return

    print(f"📊 WICS 업종분류 수집 시작 (기준일: {working_date})...")

    mapping = {}
    success_count = 0
    failed_categories = []

    for mid_cd, (large_name, mid_name) in MID_SECTORS.items():
        stocks = fetch_sector_stocks(mid_cd, working_date)
        if stocks:
            for s in stocks:
                ticker = s.get("CMP_CD", "")
                if ticker:
                    mapping[ticker] = {
                        "large": large_name,
                        "mid": mid_name,
                    }
            success_count += 1
            print(f"  ✅ {mid_name} ({large_name}): {len(stocks)}종목")
        else:
            failed_categories.append(f"{mid_name}({mid_cd})")
            print(f"  ❌ {mid_name} ({large_name}): 데이터 없음 (재시도 3회 실패)")
        time.sleep(0.5)

    total_categories = len(MID_SECTORS)
    print(f"\n📋 총 {len(mapping)}개 종목 매핑 / {success_count}/{total_categories} 카테고리 성공")
    if failed_categories:
        print(f"❌ 실패한 카테고리: {', '.join(failed_categories)}")

    # 안전망: 새 매핑이 기존보다 30%+ 감소했으면 기존 유지 (regression 방지)
    sector_map_path = DATA_DIR / "sector-map.json"
    if sector_map_path.exists():
        try:
            with open(sector_map_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            existing_count = len(existing)
            new_count = len(mapping)
            if existing_count > 0 and new_count < existing_count * 0.7:
                print(f"⚠️ 안전망 작동: 새 매핑({new_count})이 기존({existing_count}) 대비 "
                      f"{int(new_count/existing_count*100)}%로 크게 감소. 기존 매핑 유지.")
                return
        except Exception as e:
            print(f"  [WARN] 기존 sector-map.json 비교 실패: {e}")

    # 충분한 매핑 받았으면 저장
    if len(mapping) < 500:
        print(f"⚠️ 매핑 너무 적음 ({len(mapping)}개). 안전상 저장 건너뜀.")
        return

    with open(sector_map_path, "w", encoding="utf-8") as f:
        json.dump(mapping, f, ensure_ascii=False, indent=None)

    size_kb = sector_map_path.stat().st_size / 1024
    print(f"✅ sector-map.json 저장 완료 ({size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
