/* 종목 상세 — 서버 컴포넌트 껍데기.

   차트·탭 등 인터랙티브 부분은 StockClient 에 남아 있다. 여기서는 데이터를
   서버에서 읽어 필요한 만큼만 넘긴다.

   전에는 클라이언트가 stock-rankings.json 2.6MB 와 theme-map.json 69KB 를
   받아 find() 로 한 줄을 뽑았다. 방문자의 64%가 모바일인데 종목 하나 보려고
   2.7MB 를 기다린 셈이다. 그 다운로드가 통째로 사라진다.

   generateStaticParams 로 2,600 종목을 빌드 시점에 미리 만든다. 전에는 요청마다
   서버 렌더(ƒ)였다 — 첫 방문자마다 함수 호출이 일어나고, 구글봇이 2,600 페이지를
   크롤하면 그만큼 함수가 돌았다. 무료 티어에서 한도에 근접했던 이력도 있다.
*/

import { loadRankings } from "@/app/lib/seo";
import StockClient from "./StockClient";
import fs from "fs";
import path from "path";

export const dynamic = "force-static";
// 신규 상장 등 빌드 목록에 없는 종목은 요청 시 생성해 캐시한다.
export const dynamicParams = true;

export function generateStaticParams() {
  return loadRankings()
    .data.filter((s) => s.ticker)
    .map((s) => ({ ticker: s.ticker as string }));
}

/** 이 종목이 속한 테마 목록. theme-map 은 테마명 -> 티커배열 구조다. */
function themesOf(ticker: string): string[] {
  try {
    const p = path.join(process.cwd(), "public", "data", "theme-map.json");
    const map = JSON.parse(fs.readFileSync(p, "utf-8")) as Record<string, string[]>;
    return Object.entries(map)
      .filter(([, tickers]) => tickers.includes(ticker))
      .map(([name]) => name);
  } catch {
    return [];
  }
}

export default async function Page({ params }: { params: Promise<{ ticker: string }> }) {
  const { ticker } = await params;
  const stockData = loadRankings().data.find((s) => s.ticker === ticker) ?? null;
  return (
    <StockClient
      ticker={ticker}
      stockData={stockData as any}
      stockThemes={stockData ? themesOf(ticker) : []}
    />
  );
}
