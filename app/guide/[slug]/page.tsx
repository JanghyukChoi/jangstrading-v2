/* 설명 글 라우트 — 슬러그로 글을 고른다.

   폴더명에 한글을 쓰면 빌드가 InvalidCharacterError 로 죽는다(실측). 그래서
   [slug] 동적 세그먼트를 쓰고 한글은 런타임 값으로만 들어온다.
   /sectors/[name] 이 한글 URL 로 멀쩡한 것도 같은 이유다.

   글이 늘면 GUIDES 에 한 줄 추가하면 된다. 본문은 각자 파일에 있다 —
   한 파일에 다 넣으면 금방 손댈 수 없는 크기가 된다.
*/

import type { Metadata } from "next";
import AvgCostGuide, { META as avgCostMeta } from "./AvgCostGuide";
import VolatilityGuide, { META as volatilityMeta } from "./VolatilityGuide";

export const dynamic = "force-static";
export const dynamicParams = false;   // 정의한 글 외에는 404

const GUIDES = {
  "평균단가": { meta: avgCostMeta, Body: AvgCostGuide },
  "변동성": { meta: volatilityMeta, Body: VolatilityGuide },
} as const;

type Slug = keyof typeof GUIDES;

export function generateStaticParams() {
  return Object.keys(GUIDES).map((slug) => ({ slug }));
}

export async function generateMetadata(
  { params }: { params: Promise<{ slug: string }> }
): Promise<Metadata> {
  // 세그먼트가 이중 인코딩으로 들어오는 경우가 있다 — seo.ts 의 decodeSegment
  // 와 같은 문제다. 여기서는 키 조회만 하면 되므로 그때그때 풀어서 맞춰본다.
  const { slug } = await params;
  const g = GUIDES[pick(slug)];
  return g ? g.meta : {};
}

/** 인코딩 상태와 무관하게 슬러그를 찾는다. */
function pick(raw: string): Slug {
  let v = raw;
  for (let i = 0; i < 4; i++) {
    if (v in GUIDES) return v as Slug;
    let next: string;
    try {
      next = decodeURIComponent(v);
    } catch {
      break;
    }
    if (next === v) break;
    v = next;
  }
  return v as Slug;
}

export default async function Page({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const g = GUIDES[pick(slug)];
  if (!g) return null;          // dynamicParams=false 라 실제로는 도달하지 않는다
  const { Body } = g;
  return <Body />;
}
