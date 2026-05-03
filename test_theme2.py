"""네이버 테마 데이터 추출 테스트"""
import requests
from bs4 import BeautifulSoup
import re
import time

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

# 1. 테마 목록 수집 (전체 페이지)
themes = []  # (no, name)
for page in range(1, 10):
    r = requests.get(
        f'https://finance.naver.com/sise/theme.naver?page={page}',
        headers=headers
    )
    r.encoding = 'euc-kr'
    text = r.content.decode('euc-kr', errors='replace')

    matches = re.findall(r'type=theme&no=(\d+)"[^>]*>\s*([^<]+)', text)
    if not matches:
        break
    for no, name in matches:
        themes.append((no, name.strip()))
    print(f"  페이지 {page}: {len(matches)}개 테마")
    time.sleep(0.3)

print(f"\n총 {len(themes)}개 테마 발견")
for no, name in themes[:10]:
    print(f"  no={no} → {name}")
print("  ...")

# 2. 첫 번째 테마의 상세 페이지에서 종목 추출 테스트
if themes:
    test_no, test_name = themes[0]
    print(f"\n=== 테스트: {test_name} (no={test_no}) ===")
    r = requests.get(
        f'https://finance.naver.com/sise/sise_group_detail.naver?type=theme&no={test_no}',
        headers=headers
    )
    r.encoding = 'euc-kr'
    text = r.content.decode('euc-kr', errors='replace')
    soup = BeautifulSoup(text, 'html.parser')

    # 종목코드 추출 (main.naver?code=XXXXXX)
    codes = re.findall(r'main\.naver\?code=(\d{6})', text)
    unique_codes = list(set(codes))
    print(f"  종목 수: {len(unique_codes)}개")
    for c in unique_codes[:10]:
        print(f"    {c}")
