/* 섹터·테마 상세 — 서버 컴포넌트 껍데기.

   소속 종목 판정을 서버로 옮겼다. 전에는 클라이언트가 stock-rankings.json
   2.6MB + theme-map.json 69KB 를 받아 걸렀는데, 섹터 하나에 보통 수십~수백
   종목이라 나머지는 버리는 데이터였다.

   generateStaticParams 로 섹터·테마 전부를 빌드 시점에 만든다.
*/

import fs from "fs";
import path from "path";
import { loadRankings, type StockRow } from "@/app/lib/seo";
import SectorClient from "./SectorClient";

export const dynamic = "force-static";
export const dynamicParams = true;

function themeMap(): Record<string, string[]> {
  try {
    const p = path.join(process.cwd(), "public", "data", "theme-map.json");
    return JSON.parse(fs.readFileSync(p, "utf-8"));
  } catch {
    return {};
  }
}

/** 섹터(대·중분류) + 테마 이름 전체. 사이트맵과 같은 집합이어야 한다. */
function allNames(): string[] {
  const names = new Set<string>();
  for (const s of loadRankings().data) {
    if (s.sector && s.sector !== "기타") names.add(s.sector);
    if (s.sector_mid && s.sector_mid !== "기타") names.add(s.sector_mid);
  }
  for (const n of Object.keys(themeMap())) names.add(n);
  return [...names];
}

export function generateStaticParams() {
  return allNames().map((name) => ({ name: encodeURIComponent(name) }));
}

/** 테마면 티커 목록으로, 아니면 섹터 분류로 소속을 판정한다. */
function membersOf(sectorName: string): StockRow[] {
  const { data } = loadRankings();
  const tickers = themeMap()[sectorName];
  if (tickers) {
    const set = new Set(tickers);
    return data.filter((s) => s.ticker && set.has(s.ticker));
  }
  return data.filter(
    (s) => (s.sector_mid || s.sector || "기타") === sectorName || (s.sector || "기타") === sectorName
  );
}

export default async function Page({ params }: { params: Promise<{ name: string }> }) {
  const sectorName = decodeURIComponent((await params).name);
  return <SectorClient sectorName={sectorName} members={membersOf(sectorName) as any} />;
}
