/* 종목 상세의 SEO 층.

   page.tsx 는 "use client" 라 metadata 를 내보낼 수 없다(Next 는 서버
   컴포넌트에서만 허용한다). 그래서 레이아웃을 서버 컴포넌트로 두고 여기서
   메타데이터·구조화데이터·요약 텍스트를 담당한다. page.tsx 는 그대로 둔다.

   고치는 문제
     - 2,600 종목 페이지가 전부 <title>종목별 순매수 랭킹</title> 이었다.
       구글에는 2,600개 중복 페이지로 보이고 색인에서 빠진다.
     - HTML 본문에 종목명이 0회 등장했다. 데이터가 전부 클라이언트 fetch 라
       크롤러가 읽을 텍스트가 없었다.

   아래 요약 섹션은 클라이언트가 그리는 차트·표와 중복되지 않는다. 같은 숫자를
   문장으로 한 번 더 쓰는 것이라 스크린리더와 크롤러 양쪽에 도움이 된다.
*/

import type { Metadata } from "next";
import Link from "next/link";
import {
  BASE_URL,
  breadcrumb,
  findStock,
  fmtAmount,
  fmtDateKo,
  fmtPct,
  fmtPrice,
  jsonLdScript,
  loadRankings,
} from "@/app/lib/seo";

type Props = { params: Promise<{ ticker: string }> };

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { ticker } = await params;
  const s = findStock(ticker);
  const { date } = loadRankings();

  if (!s) {
    // 상장폐지·신규상장 등으로 랭킹에 없는 종목. 제목만 구분해 주고
    // 색인은 막는다 — 내용 없는 페이지가 색인되면 사이트 품질 점수가 깎인다.
    return {
      title: `${ticker} 수급 정보`,
      robots: { index: false, follow: true },
      alternates: { canonical: `${BASE_URL}/stocks/${ticker}` },
    };
  }

  const f1m = s.foreign?.["1m"];
  const i1m = s.institution?.["1m"];
  const avg = s.avg_cost;
  const parts = [
    `${s.name}(${ticker}) 외국인·기관 순매수와 추정 평균 매입가.`,
    `최근 1개월 외국인 ${fmtAmount(f1m)}, 기관 ${fmtAmount(i1m)}.`,
  ];
  if (avg?.foreign) parts.push(`외국인 추정 평균단가 ${fmtPrice(avg.foreign.avg_cost)}.`);
  if (s.per && s.per > 0) parts.push(`PER ${s.per.toFixed(1)}배.`);
  parts.push(`${fmtDateKo(date)} 기준.`);

  const title = `${s.name}(${ticker}) 외국인·기관 순매수 · 평균 매입가`;
  const description = parts.join(" ").slice(0, 155);

  return {
    title,
    description,
    // 종목코드로 직접 찾는 검색이 실제로 들어온다 — Search Console 에
    // "krx005930", "kosdaq: 126880" 형태가 잡혔다. 시장 접두어를 붙인 변형을
    // 같이 넣는다.
    keywords: [
      `${s.name} 수급`,
      `${s.name} 외국인 순매수`,
      `${s.name} 기관 순매수`,
      `${s.name} 평균단가`,
      `${s.name} 주가`,
      ticker,
      `${s.market.toLowerCase()} ${ticker}`,
      `krx${ticker}`,
      s.sector_mid ?? "",
      "투자자별 순매수",
      "외국인 매매동향",
    ].filter(Boolean),
    alternates: { canonical: `${BASE_URL}/stocks/${ticker}` },
    openGraph: {
      title,
      description,
      type: "article",
      locale: "ko_KR",
      siteName: "JangsTrading",
      url: `${BASE_URL}/stocks/${ticker}`,
    },
  };
}

export default async function Layout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ ticker: string }>;
}) {
  const { ticker } = await params;
  const s = findStock(ticker);
  const { date } = loadRankings();
  if (!s) return <>{children}</>;

  const crumbs = breadcrumb([
    { name: "홈", url: "/" },
    { name: "종목", url: "/stocks" },
    { name: s.name, url: `/stocks/${ticker}` },
  ]);

  /* Dataset 스키마 — 이 페이지가 무슨 데이터를 담고 있는지 기계가 읽는 형태.
     구글 데이터셋 검색과 AI 검색이 인용할 근거가 된다. 일반 주가 사이트는
     이걸 안 붙이므로 차별점이기도 하다. */
  const dataset = {
    "@context": "https://schema.org",
    "@type": "Dataset",
    name: `${s.name}(${ticker}) 투자자별 순매수 데이터`,
    description: `${s.name} 종목의 외국인·기관·연기금·기타법인 기간별 순매수 금액과 회전율 가중 추정 평균 매입가. ${fmtDateKo(date)} 기준.`,
    url: `${BASE_URL}/stocks/${ticker}`,
    isAccessibleForFree: true,
    inLanguage: "ko",
    creator: { "@type": "Organization", name: "JangsTrading", url: BASE_URL },
    temporalCoverage: date,
    variableMeasured: [
      { "@type": "PropertyValue", name: "외국인 순매수(1개월)", value: fmtAmount(s.foreign?.["1m"]) },
      { "@type": "PropertyValue", name: "기관 순매수(1개월)", value: fmtAmount(s.institution?.["1m"]) },
      ...(s.avg_cost?.foreign
        ? [{ "@type": "PropertyValue", name: "외국인 추정 평균단가", value: fmtPrice(s.avg_cost.foreign.avg_cost) }]
        : []),
    ],
  };

  const periods: [string, string][] = [
    ["1d", "1일"], ["1w", "1주"], ["1m", "1개월"], ["3m", "3개월"], ["6m", "6개월"],
  ];

  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdScript(crumbs) }} />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdScript(dataset) }} />
      {children}

      {/* 크롤러가 읽을 수 있는 텍스트 요약. 위 차트·표와 같은 숫자를 문장으로
          한 번 더 쓴다 — 스크린리더에도 도움이 된다. */}
      <section className="mt-4">
        <div className="bg-[var(--bg-card)] rounded-2xl p-5 sm:p-6">
          <h2 className="text-[15px] sm:text-[17px] font-semibold text-white mb-3">
            {s.name} 수급 요약
          </h2>
          <p className="text-[13px] sm:text-[14px] text-[var(--text-secondary)] leading-relaxed">
            {s.name}({ticker})은 {s.market} 상장 종목
            {s.sector_mid ? `으로 ${s.sector_mid} 업종에 속합니다` : "입니다"}.{" "}
            {fmtDateKo(date)} 기준 최근 1개월 외국인 순매수는{" "}
            <strong className="text-white">{fmtAmount(s.foreign?.["1m"])}</strong>, 기관은{" "}
            <strong className="text-white">{fmtAmount(s.institution?.["1m"])}</strong>
            {s.corp?.["1m"] ? <>, 기타법인은 <strong className="text-white">{fmtAmount(s.corp["1m"])}</strong></> : null}
            입니다.
            {s.price_change?.["1m"] != null && (
              <> 같은 기간 주가는 {fmtPct(s.price_change["1m"], 1)} 변동했습니다.</>
            )}
            {s.avg_cost?.foreign && (
              <>
                {" "}외국인의 회전율 가중 추정 평균 매입가는{" "}
                <strong className="text-white">{fmtPrice(s.avg_cost.foreign.avg_cost)}</strong>
                로, 현재가({fmtPrice(s.avg_cost.price)}) 대비{" "}
                {s.avg_cost.foreign.pnl_pct >= 0 ? "높은" : "낮은"} 수준입니다.
              </>
            )}
          </p>

          <h3 className="text-[13px] sm:text-[14px] font-semibold text-white mt-5 mb-2">
            기간별 순매수 (단위: 금액)
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-[12px] sm:text-[13px]">
              <caption className="sr-only">
                {s.name} 기간별 외국인·기관 순매수 금액
              </caption>
              <thead>
                <tr className="text-[var(--text-muted)] border-b border-white/[0.06]">
                  <th scope="col" className="text-left py-2 font-normal">기간</th>
                  <th scope="col" className="text-right py-2 font-normal">외국인</th>
                  <th scope="col" className="text-right py-2 font-normal">기관</th>
                  <th scope="col" className="text-right py-2 font-normal">주가</th>
                </tr>
              </thead>
              <tbody>
                {periods.map(([k, label]) => (
                  <tr key={k} className="border-t border-white/[0.03]">
                    <th scope="row" className="text-left py-2 font-normal text-[var(--text-secondary)]">{label}</th>
                    <td className="text-right py-2 num text-[var(--text-secondary)]">{fmtAmount(s.foreign?.[k])}</td>
                    <td className="text-right py-2 num text-[var(--text-secondary)]">{fmtAmount(s.institution?.[k])}</td>
                    <td className="text-right py-2 num text-[var(--text-secondary)]">{fmtPct(s.price_change?.[k], 1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="text-[11px] sm:text-[12px] text-[var(--text-muted)] mt-4 leading-relaxed">
            평균 매입가는 Grinblatt &amp; Han(2005)의 회전율 가중 기준가격을 투자자별로
            적용한 추정치입니다. 실제 매입 단가와 다를 수 있습니다.{" "}
            <Link href="/guide/외국인-평균단가" className="text-[var(--accent-blue)] hover:underline">
              평균단가란?
            </Link>
          </p>
        </div>
      </section>
    </>
  );
}
