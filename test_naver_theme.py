"""네이버 테마 페이지 구조 확인용 테스트 스크립트"""
import requests
from bs4 import BeautifulSoup
import re

r = requests.get(
    'https://finance.naver.com/sise/theme.naver?page=1',
    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
)
r.encoding = 'euc-kr'
text = r.content.decode('euc-kr', errors='replace')
soup = BeautifulSoup(text, 'html.parser')

print(f"=== 상태: {r.status_code}, 크기: {len(text)} ===")

# 1. type=theme 링크 찾기
theme_links = re.findall(r'type=theme&no=(\d+)', text)
print(f"\ntype=theme 링크 수: {len(theme_links)}")

# 2. 모든 링크 찾기
all_links = soup.find_all('a')
print(f"전체 링크 수: {len(all_links)}")
for a in all_links[:10]:
    href = a.get('href', '')
    txt = a.text.strip()[:30]
    if txt:
        print(f"  {href[:60]} → {txt}")

# 3. 테이블 찾기
tables = soup.find_all('table')
print(f"\n테이블 수: {len(tables)}")

# 4. iframe 찾기
iframes = soup.find_all('iframe')
print(f"iframe 수: {len(iframes)}")
for iframe in iframes:
    print(f"  src={iframe.get('src', '')}")

# 5. HTML 일부 출력 (2000~3000자)
print(f"\n=== HTML 샘플 (2000-3000) ===")
print(text[2000:3000])
