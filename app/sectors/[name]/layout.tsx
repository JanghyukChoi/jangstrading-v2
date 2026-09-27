/* 섹터·테마 상세의 SEO 층.

   섹터 31개 + 테마 264개 = 295 페이지가 전부 상위 레이아웃의 제목을 물려받아
   "섹터별 수급 현황 | JangsTrading" 하나로 중복돼 있었다.

   page.tsx 가 "use client" 라 metadata 를 못 내보내므로 레이아웃에서 처리한다.
*/

import type { Metadata } from "next";
import {
  BASE_URL, breadcrumb, fmtAmount, fmtDateKo, jsonLdScript, loadRankings,
} from "@/app/lib/seo";

type Props = { params: Promise<{ name: string }> };

/** 해당 섹터/테마에 속한 종목과 1개월 수급 합계. */
function sectorStats(name: string) {
  const { data, date } = loadRankings();
  const members = data.filter((s) => s.sector === name || s.sector_mid === name);
  const foreign = members.reduce((a, s) => a + (s.foreign?.["1m"] ?? 0), 0);
  const inst = members.reduce((a, s) => a + (s.institution?.["1m"] ?? 0), 0);
  const top = [...members]
    .sort((a, b) => (b.combined?.["1m"] ?? 0) - (a.combined?.["1m"] ?? 0))
    .slice(0, 5);
  return { members, foreign, inst, top, date };
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const name = decodeURIComponent((await params).name);
  const { members, foreign, inst, date } = sectorStats(name);

  if (members.length === 0) {
    // 테마 페이지는 theme-map 기반이라 랭킹에 매칭이 없을 수 있다.
    // 제목만 구분해 주고 색인은 허용한다(테마 목록 자체는 유효한 페이지다).
    return {
      title: `${name} 관련주 수급`,
      description: `${name} 관련 종목의 외국인·기관 순매수 현황. ${fmtDateKo(date)} 기준.`,
      alternates: { canonical: `${BASE_URL}/sectors/${encodeURIComponent(name)}` },
    };
  }

  const title = `${name} 섹터 외국인·기관 순매수 현황`;
  const description =
    `${name} 섹터 ${members.length}개 종목의 수급. 최근 1개월 외국인 ${fmtAmount(foreign)}, ` +
    `기관 ${fmtAmount(inst)}. ${fmtDateKo(date)} 기준.`;

  return {
    title,
    description: description.slice(0, 155),
    keywords: [`${name} 관련주`, `${name} 수급`, `${name} 외국인 순매수`, "섹터 수급"],
    alternates: { canonical: `${BASE_URL}/sectors/${encodeURIComponent(name)}` },
    openGraph: {
      title, description, type: "website", locale: "ko_KR", siteName: "JangsTrading",
      url: `${BASE_URL}/sectors/${encodeURIComponent(name)}`,
    },
  };
}

export default async function Layout({
  children, params,
}: { children: React.ReactNode; params: Promise<{ name: string }> }) {
  const name = decodeURIComponent((await params).name);
  const { members, foreign, inst, top, date } = sectorStats(name);

  const crumbs = breadcrumb([
    { name: "홈", url: "/" },
    { name: "섹터", url: "/sectors" },
    { name, url: `/sectors/${encodeURIComponent(name)}` },
  ]);

  const itemList = members.length
    ? {
        "@context": "https://schema.org",
        "@type": "ItemList",
        name: `${name} 섹터 순매수 상위 종목`,
        numberOfItems: top.length,
        itemListElement: top.map((s, i) => ({
          "@type": "ListItem",
          position: i + 1,
          name: s.name,
          url: `${BASE_URL}/stocks/${s.ticker}`,
        })),
      }
    : null;

  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdScript(crumbs) }} />
      {itemList && (
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdScript(itemList) }} />
      )}
      {children}

      {members.length > 0 && (
        <section className="mt-4">
          <div className="bg-[var(--bg-card)] rounded-2xl p-5 sm:p-6">
            <h2 className="text-[15px] sm:text-[17px] font-semibold text-white mb-3">
              {name} 섹터 수급 요약
            </h2>
            <p className="text-[13px] sm:text-[14px] text-[var(--text-secondary)] leading-relaxed">
              {name} 섹터에는 {members.length}개 종목이 속해 있습니다. {fmtDateKo(date)} 기준
              최근 1개월 외국인 순매수는 <strong className="text-white">{fmtAmount(foreign)}</strong>,
              기관은 <strong className="text-white">{fmtAmount(inst)}</strong>입니다.
              {top.length > 0 && (
                <> 합산 순매수 상위 종목은 {top.map((s) => s.name).join(", ")} 순입니다.</>
              )}
            </p>
          </div>
        </section>
      )}
    </>
  );
}
