/* AI 시황 리포트 상세 — 서버 컴포넌트.

   예전에는 "use client" 로 세 파일을 브라우저에서 받아 그렸다. 그중
   stock-rankings.json 이 2.4MB 인데, 본문의 종목명에 링크를 거는 용도로만
   썼다. 읽기 전용 글 한 편을 보여주려고 매번 2.4MB 를 받은 셈이다.

   전부 정적 파일이라 서버에서 읽으면 된다. 얻는 것:
     - 본문이 HTML 에 담긴다. 리포트 58편이 이 사이트의 유일한 '글' 자산인데
       그동안 크롤러에겐 빈 페이지였다.
     - 2.4MB 다운로드가 사라진다.
     - 링크 계산이 빌드 시점으로 옮겨간다.

   클라이언트가 필요했던 유일한 이유는 뒤로가기 버튼(router.back())이었다.
   목록으로 가는 Link 로 바꾸면 페이지 전체가 서버 컴포넌트가 된다 — 어차피
   대부분 목록에서 들어오므로 동작도 사실상 같다.
*/

import Link from "next/link";
import { loadReport, loadReportIndex } from "@/app/lib/reports";
import { loadRankings } from "@/app/lib/seo";
import TelegramCTA from "@/app/components/TelegramCTA";

export const dynamic = "force-static";
export const dynamicParams = true;

interface StockRef {
  name: string;
  ticker: string;
}

// 본문 텍스트에서 종목명을 찾아 Link 로 변환.
// 한글에는 word boundary 가 없어서 부분 매칭(예: "테스트"에서 "테스")이 생긴다.
// 시작 lookbehind + 끝 lookahead(조사 허용)로 막는다.
const KOREAN_JOSA = [
  // 길이 긴 것부터 (regex alternation 우선순위)
  "으로의", "이라는", "으로서", "으로써", "에서의", "에게서", "에서는", "에서도", "까지는", "까지도", "에게는", "에게도",
  "으로", "이라", "라고", "에서", "에게", "한테", "부터", "까지", "처럼", "보다", "마저", "조차", "마다", "로서", "로써", "라는",
  "은", "는", "이", "가", "을", "를", "의", "도", "만", "에", "와", "과", "로", "라", "야", "랑", "뿐", "께", "더",
];

function buildStockLinkPattern(stocks: StockRef[]): RegExp {
  const escape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const names = stocks.map((s) => escape(s.name)).join("|");
  const josa = [...KOREAN_JOSA].sort((a, b) => b.length - a.length).join("|");
  return new RegExp(
    `(?<![가-힣A-Za-z0-9])(${names})(?=$|[^가-힣A-Za-z0-9]|(?:${josa})(?![가-힣A-Za-z0-9]))`,
    "g"
  );
}

function linkifyStocks(body: string, stocks: StockRef[]): React.ReactNode[] {
  if (stocks.length === 0) return [body];
  // 긴 이름이 먼저 매칭되도록 (예: "삼성전자우"가 "삼성전자"보다 우선)
  const sorted = [...stocks].sort((a, b) => b.name.length - a.name.length);
  const pattern = buildStockLinkPattern(sorted);
  const tokens = body.split(pattern);
  const nameToTicker = new Map(sorted.map((s) => [s.name, s.ticker]));
  return tokens.map((tok, i) => {
    const ticker = nameToTicker.get(tok);
    if (ticker) {
      return (
        <Link key={i} href={`/stocks/${ticker}`} className="text-[var(--accent-blue)] hover:underline">
          {tok}
        </Link>
      );
    }
    return <span key={i}>{tok}</span>;
  });
}

export default async function ReportDetailPage({
  params,
}: {
  params: Promise<{ date: string }>;
}) {
  const { date } = await params;
  const report = loadReport(date);

  if (!report) {
    return (
      <div className="text-center py-16">
        <p className="text-[var(--text-muted)]">리포트를 찾을 수 없습니다.</p>
        <Link href="/reports" className="text-[var(--accent-blue)] mt-2 text-sm hover:underline inline-block">
          ← 시황 목록
        </Link>
      </div>
    );
  }

  const index = loadReportIndex();
  const stocks: StockRef[] = loadRankings()
    .data.filter((s) => s.ticker && s.name)
    .map((s) => ({ name: s.name, ticker: s.ticker as string }));

  const currentIdx = index.findIndex((r) => r.date === date);
  const olderReport = currentIdx >= 0 && currentIdx < index.length - 1 ? index[currentIdx + 1] : null;
  const newerReport = currentIdx > 0 ? index[currentIdx - 1] : null;

  return (
    <div className="max-w-3xl mx-auto space-y-4">
      <div className="flex items-center gap-3">
        <Link href="/reports" className="text-[var(--text-muted)] hover:text-white transition text-sm">
          ← 시황 목록
        </Link>
      </div>

      <article className="bg-[var(--bg-card)] rounded-2xl p-5 sm:p-8">
        <div className="flex items-center gap-2 mb-3">
          <time dateTime={report.date} className="text-[13px] text-[var(--text-muted)] num">{report.date}</time>
          <span className="text-[12px] text-[var(--text-muted)]">·</span>
          <span className="text-[12px] text-[var(--text-muted)]">뉴스 {report.news_count}건 참고</span>
          <span className="text-[12px] text-[var(--text-muted)]">·</span>
          <span className="text-[12px] text-[var(--text-muted)]">AI 자동 생성</span>
        </div>

        <h1 className="text-xl sm:text-2xl font-bold text-white leading-snug mb-6">{report.title}</h1>

        <div className="text-[15px] sm:text-[16px] text-[var(--text-secondary)] leading-[1.85] whitespace-pre-line">
          {linkifyStocks(report.body, stocks)}
        </div>

        <div className="mt-8 pt-4 border-t border-white/[0.04]">
          <p className="text-[12px] text-[var(--text-muted)] leading-relaxed">
            본 시황 분석은 AI가 수급 데이터와 뉴스를 기반으로 자동 생성한 참고 자료이며, 투자 권유나 추천이 아닙니다.
            투자 판단의 책임은 투자자 본인에게 있습니다.
          </p>
        </div>
      </article>

      {(olderReport || newerReport) && (
        <nav className="grid grid-cols-2 gap-3 pt-2" aria-label="이전 다음 시황">
          {olderReport ? (
            <Link
              href={`/reports/${olderReport.date}`}
              className="group flex flex-col gap-1 bg-[var(--bg-card)] rounded-2xl px-4 py-4.5 hover:border-white/[0.15] transition min-w-0"
            >
              <span className="text-[13px] text-[var(--text-muted)] group-hover:text-[var(--accent-blue)] transition">← 이전 시황</span>
              <span className="text-[13px] sm:text-[14px] text-white font-medium line-clamp-1">{olderReport.title}</span>
              <span className="text-[12px] text-[var(--text-muted)] num">{olderReport.date}</span>
            </Link>
          ) : <div />}
          {newerReport ? (
            <Link
              href={`/reports/${newerReport.date}`}
              className="group flex flex-col gap-1 bg-[var(--bg-card)] rounded-2xl px-4 py-4.5 hover:border-white/[0.15] transition min-w-0 text-right"
            >
              <span className="text-[13px] text-[var(--text-muted)] group-hover:text-[var(--accent-blue)] transition">다음 시황 →</span>
              <span className="text-[13px] sm:text-[14px] text-white font-medium line-clamp-1">{newerReport.title}</span>
              <span className="text-[12px] text-[var(--text-muted)] num">{newerReport.date}</span>
            </Link>
          ) : <div />}
        </nav>
      )}

      {/* 리포트는 커뮤니티·SNS 로 공유할 때 링크로 쓰는 페이지다.
          구독 경로를 여기에 둔다. */}
      <TelegramCTA />
    </div>
  );
}
