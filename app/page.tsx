/* 홈 — 서버 컴포넌트 껍데기.

   대시보드 자체는 인터랙티브라 HomeClient 에 남아 있다. 여기서는 크롤러와
   AI 검색이 읽을 수 있는 것들을 담당한다.

   홈은 사이트에서 권위가 가장 높은 페이지다. 여기에 종목·섹터·리포트로 가는
   서버 렌더 링크가 있어야 하위 페이지가 색인된다. 기존에는 HTML 본문이
   293자(헤더·푸터·면책문구)뿐이라 크롤러 입장에서 빈 페이지였다.
*/

import Link from "next/link";
import HomeClient from "./HomeClient";
import TelegramCTA from "./components/TelegramCTA";
import {
  BASE_URL, fmtAmount, fmtDateKo, jsonLdScript, loadRankings,
} from "./lib/seo";
import { loadReportIndex } from "./lib/reports";

export const dynamic = "force-static";


export default function Page() {
  const { data, date } = loadRankings();
  const reports = loadReportIndex().slice(0, 5);

  const withTicker = data.filter((s) => s.ticker);
  const topBuy = [...withTicker]
    .sort((a, b) => (b.combined?.["1m"] ?? 0) - (a.combined?.["1m"] ?? 0))
    .slice(0, 10);
  const topSell = [...withTicker]
    .sort((a, b) => (a.combined?.["1m"] ?? 0) - (b.combined?.["1m"] ?? 0))
    .slice(0, 10);

  const faq = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: [
      {
        "@type": "Question",
        name: "외국인·기관 순매수 데이터는 어디서 오나요?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "한국거래소(KRX) 공시 기반의 투자자별 매매동향 데이터를 매 영업일 장 마감 후 수집합니다. 외국인, 기관, 연기금, 기타법인, 개인의 종목별 순매수 금액을 기간별로 제공합니다.",
        },
      },
      {
        "@type": "Question",
        name: "추정 평균 매입가는 어떻게 계산하나요?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "Grinblatt & Han(2005)의 회전율 가중 기준가격을 투자자별로 적용합니다. 각 시점의 매수 물량이 회전율만큼 감쇠한다고 보고, 살아남은 물량의 금액가중 평균 단가를 계산합니다. 추정치이므로 실제 매입 단가와 다를 수 있습니다.",
        },
      },
      {
        "@type": "Question",
        name: "수급 데이터로 주가를 예측할 수 있나요?",
        acceptedAnswer: {
          "@type": "Answer",
          text: "본 사이트가 10.3년(2016~2026, 3,234종목) 데이터로 검정한 결과, 외국인·기관 순매수 방향으로 향후 주가를 예측하는 신호는 시장 대비 초과수익을 내지 못했습니다. 이 사이트는 수급 사실을 보여주는 도구이며 매매 신호를 제공하지 않습니다.",
        },
      },
    ],
  };

  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdScript(faq) }} />
      <HomeClient />

      {/* 홈에서 서버가 그리는 부분.

          종목 순매수/순매도 TOP 10 은 HomeClient 가 이미 그린다 — 여기서 또
          그렸다가 같은 10종목이 화면에 두 번 나왔다. 지웠다.
          리포트 목록과 사이트 설명만 남긴다. */}
      <section className="mt-4 space-y-4">
        <TelegramCTA />

        {reports.length > 0 && (
          <div className="bg-[var(--bg-card)] rounded-2xl p-4 sm:p-6">
            <h2 className="text-[15px] sm:text-[17px] font-semibold text-white">최근 시황 리포트</h2>
            <p className="text-[12px] text-[var(--text-muted)] mb-3">매 영업일 자동 생성</p>
            <div className="space-y-0">
              {reports.map((r) => (
                <Link
                  key={r.date}
                  href={`/reports/${r.date}`}
                  className="flex items-baseline gap-3 py-2.5 border-t border-white/[0.03] first:border-0 group"
                >
                  <time dateTime={r.date} className="num text-xs text-[var(--text-muted)] shrink-0 w-[68px]">
                    {r.date.slice(2)}
                  </time>
                  <span className="text-[13px] sm:text-[14px] text-[var(--text-secondary)] group-hover:text-[var(--accent-blue)] transition line-clamp-1">
                    {r.title}
                  </span>
                </Link>
              ))}
            </div>
          </div>
        )}

        <div className="bg-[var(--bg-card)] rounded-2xl p-4 sm:p-6">
          <p className="text-[13px] sm:text-[14px] text-[var(--text-secondary)] leading-[1.8]">
            JangsTrading은 한국거래소(KRX) 공시 기반 투자자별 매매동향을 매 영업일 정리합니다.
            외국인·기관·연기금·기타법인의 종목별 순매수 금액, 시가총액 대비 비중,{" "}
            <Link href="/guide/평균단가" className="text-[var(--accent-blue)] hover:underline">
              회전율 가중 추정 평균 매입가
            </Link>
            , 섹터·테마별 자금 흐름을 무료로 제공합니다.
          </p>
        </div>
      </section>
    </>
  );
}
