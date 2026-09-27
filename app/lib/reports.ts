/* 서버 전용 — AI 시황 리포트 읽기.

   리포트 58편은 이 사이트에서 유일하게 '글'인 자산이다. 종목 페이지가
   숫자 위주라면 리포트는 문장이라 검색·AI 인용에 훨씬 유리한데, 지금까지
   메타데이터도 구조화데이터도 없었다.
*/

import fs from "fs";
import path from "path";

export interface Report {
  date: string;
  title: string;
  body: string;
  generated_at?: string;
  news_count?: number;
}

const dir = () => path.join(process.cwd(), "public", "data", "reports");

export function loadReportIndex(): { date: string; title: string }[] {
  try {
    return JSON.parse(fs.readFileSync(path.join(dir(), "index.json"), "utf-8"));
  } catch {
    return [];
  }
}

export function loadReport(date: string): Report | null {
  // 경로 조작 방지 — date 는 URL 세그먼트라 그대로 파일명에 쓰면 안 된다.
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return null;
  try {
    return JSON.parse(fs.readFileSync(path.join(dir(), `${date}.json`), "utf-8"));
  } catch {
    return null;
  }
}

/** 본문에서 [섹션제목] 줄과 마크다운 기호를 걷어낸 순수 텍스트. 요약문용. */
export function plainText(body: string): string {
  return body
    .replace(/^\[[^\]\n]+\]\s*$/gm, " ")
    .replace(/[#*_`>-]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}
