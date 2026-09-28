import type { Metadata } from "next";
import { BASE_URL, breadcrumb, jsonLdScript, loadRankings } from "@/app/lib/seo";

export const metadata: Metadata = {
  // 실측 검색어가 "투자자 별 순매수 상위 종목", "외국인/기관 연속 순매수 상위 20 종목"
  // 형태였다. 제목을 그 표현에 맞춘다(2026-09-28 Search Console 기준).
  title: "외국인·기관 순매수 상위 종목 — 투자자별 매매동향",
  description:
    "외국인·기관·연기금·기타법인 순매수 종목 랭킹. 기간별 순매수 금액과 시총 대비 비중, 외국인·기관 추정 평균 매입가를 한눈에 확인하세요.",
  alternates: { canonical: `${BASE_URL}/stocks` },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  // 이 레이아웃은 /stocks 와 /stocks/[ticker] 를 모두 감싼다. 목록 전용
  // 화면 요소를 여기 두면 종목 상세 2,600 페이지에도 그대로 붙는다.
  // 그래서 여기에는 메타데이터와 구조화데이터만 둔다.
  const { data, date } = loadRankings();

  const byForeign = [...data]
    .filter((s) => s.ticker)
    .sort((a, b) => (b.foreign?.["1m"] ?? 0) - (a.foreign?.["1m"] ?? 0));
  const topBuy = byForeign.slice(0, 20);
  const topSell = byForeign.slice(-20).reverse();

  const crumbs = breadcrumb([
    { name: "홈", url: "/" },
    { name: "종목", url: "/stocks" },
  ]);

  const itemList = {
    "@context": "https://schema.org",
    "@type": "ItemList",
    name: `외국인 순매수 상위 종목 (${date} 기준)`,
    numberOfItems: topBuy.length,
    itemListElement: topBuy.map((s, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: s.name,
      url: `${BASE_URL}/stocks/${s.ticker}`,
    })),
  };

  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdScript(crumbs) }} />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdScript(itemList) }} />
      {children}

    </>
  );
}
