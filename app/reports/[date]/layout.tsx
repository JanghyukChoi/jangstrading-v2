/* AI 시황 리포트 상세의 SEO 층.

   page.tsx 가 "use client" 라 metadata 를 못 내보낸다. 레이아웃을 서버
   컴포넌트로 두고 여기서 처리한다.

   리포트는 이 사이트에서 유일한 '글' 자산이다(58편). NewsArticle 스키마를
   붙이면 구글 뉴스·디스커버와 AI 검색이 인용할 수 있는 형태가 된다.
*/

import type { Metadata } from "next";
import { BASE_URL, breadcrumb, fmtDateKo, jsonLdScript } from "@/app/lib/seo";
import { loadReport, plainText } from "@/app/lib/reports";

type Props = { params: Promise<{ date: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { date } = await params;
  const r = loadReport(date);
  if (!r) {
    return {
      title: `${date} 시황`,
      robots: { index: false, follow: true },
      alternates: { canonical: `${BASE_URL}/reports/${date}` },
    };
  }

  const description = plainText(r.body).slice(0, 155);
  return {
    title: `${r.title} — ${fmtDateKo(r.date)} 수급 시황`,
    description,
    alternates: { canonical: `${BASE_URL}/reports/${date}` },
    openGraph: {
      title: r.title,
      description,
      type: "article",
      locale: "ko_KR",
      siteName: "JangsTrading",
      url: `${BASE_URL}/reports/${date}`,
      publishedTime: r.generated_at || `${r.date}T09:00:00+09:00`,
    },
  };
}

export default async function Layout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ date: string }>;
}) {
  const { date } = await params;
  const r = loadReport(date);
  if (!r) return <>{children}</>;

  const article = {
    "@context": "https://schema.org",
    "@type": "NewsArticle",
    headline: r.title,
    datePublished: r.generated_at || `${r.date}T09:00:00+09:00`,
    dateModified: r.generated_at || `${r.date}T09:00:00+09:00`,
    inLanguage: "ko",
    articleSection: "증시",
    description: plainText(r.body).slice(0, 200),
    url: `${BASE_URL}/reports/${date}`,
    mainEntityOfPage: { "@type": "WebPage", "@id": `${BASE_URL}/reports/${date}` },
    publisher: { "@type": "Organization", name: "JangsTrading", url: BASE_URL },
    author: { "@type": "Organization", name: "JangsTrading" },
    isAccessibleForFree: true,
  };

  const crumbs = breadcrumb([
    { name: "홈", url: "/" },
    { name: "시황 리포트", url: "/reports" },
    { name: fmtDateKo(r.date), url: `/reports/${date}` },
  ]);

  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdScript(crumbs) }} />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdScript(article) }} />
      {children}
    </>
  );
}
