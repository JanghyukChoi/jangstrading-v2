/* 사이트맵.

   고친 것 두 가지 (2026-09-28, Search Console 실측 후)

   1) `?view=mid` / `?view=theme` 제거.
      두 URL 은 /sectors 와 같은 페이지이고 canonical 도 /sectors 를 가리킨다.
      사이트맵에 넣으면 구글이 크롤한 뒤 "적절한 표준 태그가 포함된 대체
      페이지"로 분류해 버린다 — 실제로 그 분류에 50건이 잡혀 있었다.
      크롤 예산만 쓰고 얻는 게 없다.

   2) lastModified 를 실제 변경 시점으로.
      전에는 3,002개 전부에 빌드 시각(now)을 박았다. 매일 빌드하므로 구글에겐
      "3,002 페이지가 매일 전부 바뀐다"는 신호였는데, 리포트는 한 번 쓰면
      안 바뀐다. 사실과 다른 신호를 계속 주면 구글이 lastModified 자체를
      무시하기 시작한다. 이제 수급 데이터 기준일과 리포트 발행일을 쓴다.

   changeFrequency 는 구글이 오래전부터 무시하는 필드지만, 다른 크롤러
   (네이버·빙)가 참고하므로 사실에 맞게 남겨 둔다.
*/

import type { MetadataRoute } from "next";
import fs from "fs";
import path from "path";

const BASE = "https://www.jangstrading.com";

function readJson<T>(...segs: string[]): T | null {
  try {
    return JSON.parse(fs.readFileSync(path.join(process.cwd(), ...segs), "utf-8")) as T;
  } catch {
    return null;
  }
}

export default function sitemap(): MetadataRoute.Sitemap {
  const rankings = readJson<{ date: string; data: any[] }>("public", "data", "stock-rankings.json");
  const themes = readJson<Record<string, unknown>>("public", "data", "theme-map.json");
  const reports = readJson<{ date: string }[]>("public", "data", "reports", "index.json");

  // 수급 데이터 기준일. 이게 실제로 페이지 내용이 바뀐 시점이다.
  const dataDate = rankings?.date ? new Date(`${rankings.date}T09:00:00+09:00`) : new Date();

  const pages: MetadataRoute.Sitemap = [
    { url: BASE, lastModified: dataDate, changeFrequency: "daily", priority: 1.0 },
    { url: `${BASE}/stocks`, lastModified: dataDate, changeFrequency: "daily", priority: 0.9 },
    { url: `${BASE}/sectors`, lastModified: dataDate, changeFrequency: "daily", priority: 0.9 },
    { url: `${BASE}/screener`, lastModified: dataDate, changeFrequency: "daily", priority: 0.7 },
    { url: `${BASE}/reports`, lastModified: dataDate, changeFrequency: "daily", priority: 0.8 },
    // 설명 페이지. 내용이 거의 안 바뀌지만 예시 수치가 매일 갱신된다.
    ...["평균단가", "변동성"].map((slug) => ({
      url: `${BASE}/guide/${encodeURIComponent(slug)}`,
      lastModified: dataDate,
      changeFrequency: "monthly" as const,
      priority: 0.8,
    })),
  ];

  // 종목 상세 — 매 영업일 수급이 갱신되므로 daily 가 사실이다.
  for (const s of rankings?.data ?? []) {
    if (!s.ticker) continue;
    pages.push({
      url: `${BASE}/stocks/${s.ticker}`,
      lastModified: dataDate,
      changeFrequency: "daily",
      priority: 0.6,
    });
  }

  // 섹터(대·중분류) + 테마. 중복 제거해서 같은 이름이 두 번 들어가지 않게 한다.
  const sectorNames = new Set<string>();
  for (const s of rankings?.data ?? []) {
    if (s.sector && s.sector !== "기타") sectorNames.add(s.sector);
    if (s.sector_mid && s.sector_mid !== "기타") sectorNames.add(s.sector_mid);
  }
  for (const name of Object.keys(themes ?? {})) sectorNames.add(name);
  for (const name of sectorNames) {
    pages.push({
      url: `${BASE}/sectors/${encodeURIComponent(name)}`,
      lastModified: dataDate,
      changeFrequency: "daily",
      priority: 0.7,
    });
  }

  // 리포트 — 발행 후 바뀌지 않는다. 자기 날짜를 쓴다.
  for (const r of reports ?? []) {
    pages.push({
      url: `${BASE}/reports/${r.date}`,
      lastModified: new Date(`${r.date}T09:00:00+09:00`),
      changeFrequency: "never",
      priority: 0.5,
    });
  }

  return pages;
}
