import type { Metadata } from "next";
import Link from "next/link";
import { BASE_URL, breadcrumb, fmtDateKo, jsonLdScript } from "@/app/lib/seo";
import { loadReportIndex } from "@/app/lib/reports";

export const metadata: Metadata = {
  // "시황분석" 으로 유입된 기록이 있다.
  title: "오늘의 증시 시황 분석 — 외국인·기관 수급 리포트",
  description:
    "매일 수급 데이터와 뉴스를 기반으로 자동 생성되는 AI 시황 리포트. 외국인·기관 자금 흐름과 섹터별 변화를 정리합니다.",
  alternates: { canonical: `${BASE_URL}/reports` },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  const index = loadReportIndex();
  const crumbs = breadcrumb([
    { name: "홈", url: "/" },
    { name: "시황 리포트", url: "/reports" },
  ]);

  const list = {
    "@context": "https://schema.org",
    "@type": "ItemList",
    name: "JangsTrading AI 시황 리포트",
    numberOfItems: index.length,
    itemListElement: index.slice(0, 30).map((r, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: r.title,
      url: `${BASE_URL}/reports/${r.date}`,
    })),
  };

  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdScript(crumbs) }} />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdScript(list) }} />
      {children}

      {/* 리포트 58편으로 가는 서버 렌더 링크. 제목 자체가 검색어와 겹치는
          문장이라 크롤러에게 가장 값나가는 텍스트다. */}
      {index.length > 0 && (
        <section className="mt-4">
          <div className="bg-[var(--bg-card)] rounded-2xl p-5 sm:p-6">
            <h2 className="text-[15px] sm:text-[17px] font-semibold text-white mb-4">
              지난 시황 리포트 {index.length}편
            </h2>
            <ul className="space-y-2">
              {index.map((r) => (
                <li key={r.date} className="text-[13px] leading-relaxed">
                  <Link href={`/reports/${r.date}`} className="text-[var(--text-secondary)] hover:text-[var(--accent-blue)] transition">
                    <time dateTime={r.date} className="num text-[var(--text-muted)] mr-2">{r.date}</time>
                    {r.title}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </section>
      )}
    </>
  );
}
