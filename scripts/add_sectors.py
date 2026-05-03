"""
stock-rankings.json에 업종(sector) 필드를 추가하는 스크립트
public/data/sector-map.json (티커→업종 매핑)을 읽어서 적용

CSV를 갱신하려면:
  1. data.krx.co.kr → 기본통계 → 주식 → 업종분류 현황
  2. KOSPI/KOSDAQ 각각 CSV 다운로드
  3. 이 스크립트 상단의 CSV 파싱 코드로 sector-map.json 재생성

실행: python scripts/add_sectors.py
"""

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "public" / "data"

def main():
    rankings_path = DATA_DIR / "stock-rankings.json"
    sector_map_path = DATA_DIR / "sector-map.json"

    if not sector_map_path.exists():
        print("❌ sector-map.json이 없습니다. public/data/에 넣어주세요.")
        return

    with open(rankings_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    with open(sector_map_path, "r", encoding="utf-8") as f:
        sector_map = json.load(f)

    print(f"📅 기준일: {data['date']}")
    print(f"📋 섹터 매핑: {len(sector_map)}개 종목")

    matched = 0
    for item in data["data"]:
        ticker = item.get("ticker", "")
        if ticker and ticker in sector_map:
            item["sector"] = sector_map[ticker]
            matched += 1
        else:
            item.setdefault("sector", "기타")

    print(f"✅ {matched}/{len(data['data'])} 종목 섹터 매칭 완료")

    with open(rankings_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, default=str)

    size_kb = rankings_path.stat().st_size / 1024
    print(f"✅ stock-rankings.json 갱신 완료 ({size_kb:.1f} KB)")

if __name__ == "__main__":
    main()
