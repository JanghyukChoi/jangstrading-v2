/* 서버 전용 SEO 헬퍼.

   이 파일은 서버 컴포넌트에서만 import 한다 — fs 를 쓰기 때문에 클라이언트
   번들에 들어가면 빌드가 깨진다.

   왜 필요한가: 사이트의 모든 페이지가 "use client" 라서 HTML 본문이 290자뿐이었고
   (헤더·푸터·면책문구), 종목 상세 2,600 페이지가 전부 같은 <title> 을 달고 있었다.
   구글 눈에는 2,600개 중복 페이지다. 여기서 만든 메타데이터·구조화데이터·요약
   텍스트가 그 구멍을 메운다.
*/

import fs from "fs";
import path from "path";

export const BASE_URL = "https://www.jangstrading.com";
export const SITE_NAME = "JangsTrading";

export interface StockRow {
  ticker?: string;
  name: string;
  market: string;
  per?: number | null;
  pbr?: number | null;
  market_cap?: number | null;
  sector?: string;
  sector_mid?: string;
  foreign: Record<string, number>;
  institution: Record<string, number>;
  combined: Record<string, number>;
  pension?: Record<string, number>;
  corp?: Record<string, number>;
  price_change?: Record<string, number>;
  avg_cost?: {
    price: number;
    foreign?: { avg_cost: number; pnl_pct: number };
    institution?: { avg_cost: number; pnl_pct: number };
  };
}

interface Rankings {
  date: string;
  data: StockRow[];
}

/* 빌드/요청마다 파일을 다시 읽지 않도록 모듈 스코프에 캐시한다.
   2,600 종목 × 여러 페이지를 렌더할 때 같은 3MB 파일을 반복해서 파싱하면
   빌드가 눈에 띄게 느려진다. */
let cache: Rankings | null = null;

export function loadRankings(): Rankings {
  if (cache) return cache;
  try {
    const p = path.join(process.cwd(), "public", "data", "stock-rankings.json");
    cache = JSON.parse(fs.readFileSync(p, "utf-8")) as Rankings;
  } catch {
    cache = { date: "", data: [] };
  }
  return cache;
}

export function findStock(ticker: string): StockRow | null {
  return loadRankings().data.find((s) => s.ticker === ticker) ?? null;
}

/** 백만원 단위 값을 한국어 표기로. 검색 스니펫에 그대로 들어간다. */
export function fmtAmount(millionWon: number | null | undefined): string {
  if (millionWon == null || !Number.isFinite(millionWon)) return "-";
  const won = millionWon * 1_000_000;
  const abs = Math.abs(won);
  const sign = won > 0 ? "+" : won < 0 ? "-" : "";
  if (abs >= 1e12) return `${sign}${(abs / 1e12).toFixed(1)}조원`;
  if (abs >= 1e8) return `${sign}${Math.round(abs / 1e8).toLocaleString("ko-KR")}억원`;
  if (abs >= 1e4) return `${sign}${Math.round(abs / 1e4).toLocaleString("ko-KR")}만원`;
  return `${sign}${Math.round(abs).toLocaleString("ko-KR")}원`;
}

export function fmtPrice(won: number | null | undefined): string {
  if (won == null || !Number.isFinite(won)) return "-";
  return `${Math.round(won).toLocaleString("ko-KR")}원`;
}

export function fmtPct(v: number | null | undefined, digits = 2): string {
  if (v == null || !Number.isFinite(v)) return "-";
  return `${v > 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

/** "2026-09-23" -> "2026년 9월 23일" */
export function fmtDateKo(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return iso;
  return `${m[1]}년 ${Number(m[2])}월 ${Number(m[3])}일`;
}

/* JSON-LD 를 <script> 로 직렬화한다.

   Next 문서 권고대로 '<' 를 < 로 치환한다. 종목명·섹터명이 데이터에서
   오므로 이론적으로 </script> 주입이 가능하다 — 지금 데이터에는 없지만
   방어해 두는 비용이 0 이다. */
export function jsonLdScript(data: unknown): string {
  return JSON.stringify(data).replace(/</g, "\\u003c");
}

/** 홈 > 상위 > 현재 형태의 빵부스러기. 구글 검색결과에 경로로 노출된다. */
export function breadcrumb(items: { name: string; url: string }[]) {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((it, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: it.name,
      item: `${BASE_URL}${it.url}`,
    })),
  };
}
