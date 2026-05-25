"""
시황 리포트 미리보기 (저장 안 함)

실행:
  export ANTHROPIC_API_KEY="sk-..."
  python scripts/preview_report.py

또는 Windows PowerShell:
  $env:ANTHROPIC_API_KEY="sk-..."
  python scripts/preview_report.py

출력:
- 콘솔에 제목·본문 출력
- scripts/_preview.json 에 결과 저장 (git ignore 권장)
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_report import extract_key_data, crawl_news, generate_with_claude

OUT_PATH = Path(__file__).resolve().parent / "_preview.json"


def main():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("[ERROR] ANTHROPIC_API_KEY 환경변수 필요")
        print("  PowerShell: $env:ANTHROPIC_API_KEY = 'sk-...'")
        print("  Bash:       export ANTHROPIC_API_KEY=sk-...")
        return

    t0 = time.time()
    print("=" * 70)
    print("[1/3] 수급 데이터 추출")
    print("=" * 70)
    date, data_summary = extract_key_data()
    print(f"  기준일: {date}")
    print(f"  데이터 요약: {len(data_summary)}자")
    print()

    print("=" * 70)
    print("[2/3] 뉴스 본문 크롤링 (20건)")
    print("=" * 70)
    t1 = time.time()
    news = crawl_news(max_items=20)
    print(f"  추출: {len(news)}건 ({time.time() - t1:.1f}초)")
    if news:
        avg = sum(len(n["body"]) for n in news) // len(news)
        print(f"  평균 본문: {avg:,}자")
        print(f"  샘플 (#1): {news[0]['title']}")
    print()

    print("=" * 70)
    print("[3/3] Claude Sonnet 4.6 호출")
    print("=" * 70)
    t2 = time.time()
    report = generate_with_claude(date, data_summary, news)
    print(f"  소요: {time.time() - t2:.1f}초")
    print()

    if not report:
        print("[FAIL] 리포트 생성 실패")
        return

    title = report["title"]
    body = report["body"]
    print("=" * 70)
    print(f"제목: {title}")
    print("=" * 70)
    print()
    print(body)
    print()
    print("=" * 70)
    print(f"[STATS] 본문 {len(body):,}자 · 전체 소요 {time.time() - t0:.1f}초")
    print("=" * 70)

    # 미리보기 파일 저장
    OUT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n[SAVED] {OUT_PATH}")


if __name__ == "__main__":
    main()
