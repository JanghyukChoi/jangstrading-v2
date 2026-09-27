import type { Metadata } from "next";
import Link from "next/link";
import {
  BASE_URL, breadcrumb, fmtAmount, fmtDateKo, jsonLdScript, loadRankings,
} from "@/app/lib/seo";

export const metadata: Metadata = {
  title: "종목별 순매수 랭킹",
  description:
    "외국인·기관·연기금·기타법인 순매수 종목 랭킹. 기간별 순매수 금액과 시총 대비 비중, 외국인·기관 추정 평균 매입가를 한눈에 확인하세요.",
  alternates: { canonical: `${BASE_URL}/stocks` },
};

export default function Layout({ children }: { children: React.ReactNode }) {
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

      {/* 종목 상세로 가는 서버 렌더 링크.

          이게 없으면 2,600개 종목 페이지로 가는 경로가 사이트맵뿐이다. 위
          랭킹 표는 클라이언트가 그려서 크롤러가 링크를 따라가지 못한다.
          사람에게도 "지금 수급이 몰린 곳" 바로가기라 쓸모가 있다. */}
      {topBuy.length > 0 && (
        <section className="mt-4">
          <div className="bg-[var(--bg-card)] rounded-2xl p-5 sm:p-6">
            <h2 className="text-[15px] sm:text-[17px] font-semibold text-white mb-1">
              최근 1개월 수급 상위 종목
            </h2>
            <p className="text-[12px] text-[var(--text-muted)] mb-4">
              {fmtDateKo(date)} 기준 · 외국인 순매수 금액 순
            </p>

            <h3 className="text-[13px] font-semibold text-white mb-2">외국인 순매수 상위</h3>
            <ul className="flex flex-wrap gap-x-3 gap-y-1.5 mb-5">
              {topBuy.map((s) => (
                <li key={s.ticker} className="text-[13px]">
                  <Link href={`/stocks/${s.ticker}`} className="text-[var(--text-secondary)] hover:text-[var(--accent-blue)] transition">
                    {s.name}
                  </Link>
                  <span className="text-[var(--text-muted)] ml-1 num text-[12px]">
                    {fmtAmount(s.foreign?.["1m"])}
                  </span>
                </li>
              ))}
            </ul>

            <h3 className="text-[13px] font-semibold text-white mb-2">외국인 순매도 상위</h3>
            <ul className="flex flex-wrap gap-x-3 gap-y-1.5">
              {topSell.map((s) => (
                <li key={s.ticker} className="text-[13px]">
                  <Link href={`/stocks/${s.ticker}`} className="text-[var(--text-secondary)] hover:text-[var(--accent-blue)] transition">
                    {s.name}
                  </Link>
                  <span className="text-[var(--text-muted)] ml-1 num text-[12px]">
                    {fmtAmount(s.foreign?.["1m"])}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}
    </>
  );
}
