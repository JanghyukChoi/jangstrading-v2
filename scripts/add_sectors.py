"""
stock-rankings.json에 WICS 업종(대분류/중분류) 필드를 추가하는 스크립트
sector-map.json에서 매핑 데이터를 읽어 적용

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
        print("❌ sector-map.json이 없습니다. 먼저 python scripts/fetch_wics.py를 실행하세요.")
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
            s = sector_map[ticker]
            item["sector"] = s.get("large", "기타")
            item["sector_mid"] = s.get("mid", "기타")
            matched += 1
        else:
            item["sector"] = "기타"
            item["sector_mid"] = "기타"

    print(f"✅ {matched}/{len(data['data'])} 종목 섹터 매칭 완료")

    with open(rankings_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, default=str)

    size_kb = rankings_path.stat().st_size / 1024
    print(f"✅ stock-rankings.json 갱신 완료 ({size_kb:.1f} KB)")

if __name__ == "__main__":
    main()
