/* 외국인 평균단가 설명 페이지.

   읽기 전용 긴 글이라 서버 컴포넌트다. 레이아웃은 리포트 상세와 같은 기준을
   쓴다 — max-w-3xl(읽기 좋은 줄 길이), 16px, 줄간격 1.85, 카드 하나.
   대시보드처럼 여러 박스로 쪼개면 긴 글에서는 읽기 흐름이 끊긴다.

   내부 링크: 종목 상세 2,600 페이지의 평균단가 설명에서 이리로 온다.
   그게 이 페이지가 사이트 안에서 권위를 얻는 경로다.

   라우트를 [slug] 동적 세그먼트로 둔 이유: 폴더명에 한글을 쓰면 빌드가
   InvalidCharacterError 로 죽는다(실측). /sectors/[name] 이 한글 URL 을
   쓰면서 멀쩡한 것도 같은 이유 — 세그먼트 값은 런타임에 들어오기 때문이다.
   설명 글이 늘면 SLUG 상수에 추가하면 된다.
*/

import type { Metadata } from "next";
import Link from "next/link";
import {
  BASE_URL, breadcrumb, fmtDateKo, fmtPrice, jsonLdScript, loadRankings,
} from "@/app/lib/seo";

export const dynamic = "force-static";
export const dynamicParams = false;   // 정의한 글 외에는 404

const SLUG = "평균단가";
const PATH = `/guide/${SLUG}`;
const TITLE = "외국인·기관 평균단가란? — 계산 방법과 보는 법";
const DESC =
  "외국인·기관 투자자가 보유 주식을 평균 얼마에 샀는지 추정하는 방법. " +
  "회전율 가중 기준가격(Grinblatt & Han, 2005) 계산 방식과 실제 종목 예시로 설명합니다.";

export const metadata: Metadata = {
  title: TITLE,
  description: DESC,
  keywords: [
    "외국인 평균단가", "기관 평균단가", "평균 매입가", "외국인 매수 단가",
    "기관 매수 단가", "평균단가",
    "회전율 가중 기준가격", "수급 분석", "투자자별 매매동향",
  ],
  alternates: { canonical: `${BASE_URL}${PATH}` },
  openGraph: {
    title: TITLE, description: DESC, type: "article",
    locale: "ko_KR", siteName: "JangsTrading", url: `${BASE_URL}${PATH}`,
  },
};

const FAQ = [
  {
    q: "평균단가는 공시되는 값인가요?",
    a: "아닙니다. 한국거래소는 투자자별 일일 매수·매도 금액과 수량을 공시하지만 평균 매입 단가는 공시하지 않습니다. 이 사이트의 평균단가는 공시된 일별 매매 기록을 누적해 계산한 추정치입니다.",
  },
  {
    q: "왜 단순 평균이 아니라 회전율로 가중하나요?",
    a: "오래전에 매수한 물량은 이미 팔렸을 가능성이 높기 때문입니다. 단순 평균은 3년 전 매수와 어제 매수를 똑같이 취급하지만, 실제로 지금 남아 있는 물량은 최근 매수분에 가깝습니다. 회전율 가중은 각 매수 시점의 물량이 지금까지 남아 있을 확률을 가중치로 씁니다.",
  },
  {
    q: "외국인과 기관의 계산 방식이 다른가요?",
    a: "이탈률을 구하는 방법이 다릅니다. 외국인은 보유 주식 수가 공시되므로 실제 매도량 대비 보유량으로 계산합니다. 기관은 보유량 공시가 없어 시장 전체 회전율(거래량 ÷ 상장주식수)로 근사합니다.",
  },
  {
    q: "현재가가 평균단가보다 높으면 어떤 의미인가요?",
    a: "해당 투자자가 보유 물량에서 평가이익 구간에 있다는 뜻입니다. 반대로 낮으면 평가손실 구간입니다. 현재 상태를 보여주는 사실 정보입니다.",
  },
];

export function generateStaticParams() {
  return [{ slug: SLUG }];
}

export default function Page() {
  const { data, date } = loadRankings();
  const samsung = data.find((s) => s.ticker === "005930");
  const ac = samsung?.avg_cost;

  const crumbs = breadcrumb([
    { name: "홈", url: "/" },
    { name: "평균단가", url: PATH },
  ]);

  const article = {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: TITLE,
    description: DESC,
    inLanguage: "ko",
    url: `${BASE_URL}${PATH}`,
    mainEntityOfPage: { "@type": "WebPage", "@id": `${BASE_URL}${PATH}` },
    publisher: { "@type": "Organization", name: "JangsTrading", url: BASE_URL },
    author: { "@type": "Organization", name: "JangsTrading" },
    citation:
      "Grinblatt, M., & Han, B. (2005). Prospect theory, mental accounting, and momentum. Journal of Financial Economics, 78(2), 311-339.",
  };

  const faqLd = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: FAQ.map((f) => ({
      "@type": "Question",
      name: f.q,
      acceptedAnswer: { "@type": "Answer", text: f.a },
    })),
  };

  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdScript(crumbs) }} />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdScript(article) }} />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdScript(faqLd) }} />

      <div className="max-w-3xl mx-auto space-y-4">
        <Link href="/stocks" className="text-[var(--text-muted)] hover:text-white transition text-sm inline-block">
          ← 종목 목록
        </Link>

        <article className="bg-[var(--bg-card)] rounded-2xl p-5 sm:p-8">
          <h1 className="text-xl sm:text-2xl font-bold text-white leading-snug">
            외국인·기관 평균단가란?
          </h1>

          {/* 한 줄 답. 스캔하는 사람이 여기서 끝낼 수 있어야 한다. */}
          <p className="mt-4 text-[15px] sm:text-[16px] text-[var(--text-secondary)] leading-[1.85]">
            외국인과 기관이 지금 들고 있는 주식을 <strong className="text-white">평균 얼마에 샀는지</strong>{" "}
            추정한 값입니다. 현재가가 이보다 높으면 그 투자자는 평가이익 구간에, 낮으면 평가손실 구간에 있습니다.
          </p>

          {ac?.foreign && samsung && (
            <div className="mt-5 rounded-xl bg-white/[0.03] px-5 py-4">
              <p className="text-[12px] text-[var(--text-muted)] mb-3">
                예시 · {samsung.name} · {fmtDateKo(date)} 기준 · 현재가{" "}
                <span className="num text-[var(--text-secondary)]">{fmtPrice(ac.price)}</span>
              </p>
              <div className="space-y-0">
                {([
                  ["외국인", ac.foreign],
                  ["기관", ac.institution],
                ] as const).map(([label, v]) =>
                  v ? (
                    <div key={label} className="flex items-center gap-3 py-2.5 border-t border-white/[0.04] first:border-0">
                      <span className="text-[13px] sm:text-[14px] text-[var(--text-secondary)] w-14 shrink-0">
                        {label}
                      </span>
                      <span className="flex-1 text-[15px] sm:text-[17px] font-semibold text-white num">
                        {fmtPrice(v.avg_cost)}
                      </span>
                      <span className={`shrink-0 text-[13px] sm:text-[14px] num ${v.pnl_pct >= 0 ? "positive" : "negative"}`}>
                        {v.pnl_pct > 0 ? "+" : ""}{v.pnl_pct.toFixed(1)}%
                      </span>
                    </div>
                  ) : null
                )}
              </div>
              <p className="text-[12px] text-[var(--text-muted)] mt-3 leading-relaxed">
                두 주체의 평균단가가 다른 것은 서로 다른 구간에서 매수했기 때문입니다.
              </p>
            </div>
          )}

          <h2 className="text-[17px] sm:text-[19px] font-semibold text-white mt-9 mb-3">
            순매수 금액만으로는 부족한 이유
          </h2>
          <p className="text-[15px] sm:text-[16px] text-[var(--text-secondary)] leading-[1.85]">
            대부분의 수급 데이터는 &quot;외국인이 이 종목을 1,000억원어치 샀다&quot;까지만 알려줍니다.
            그런데 같은 1,000억원이라도 고점에서 샀는지 저점에서 샀는지에 따라 의미가 완전히 다릅니다.
            평균단가는 그 차이를 숫자 하나로 보여줍니다.
          </p>

          <h2 className="text-[17px] sm:text-[19px] font-semibold text-white mt-9 mb-3">
            단순 평균으로 계산하면 안 되는 이유
          </h2>
          <p className="text-[15px] sm:text-[16px] text-[var(--text-secondary)] leading-[1.85]">
            매수 금액을 매수 수량으로 나누는 단순 평균은 세 지점에서 어긋납니다.
          </p>
          <ol className="mt-4 space-y-4 text-[15px] sm:text-[16px] text-[var(--text-secondary)] leading-[1.75]">
            <li>
              <strong className="text-white">이미 보유한 물량을 무시합니다.</strong> 외국인은 삼성전자
              상장주식의 절반 가까이를 이미 들고 있습니다. 최근 몇 달만 보고 계산하면 그 이전에 쌓인
              물량이 통째로 빠집니다.
            </li>
            <li>
              <strong className="text-white">오래된 매수와 최근 매수를 같게 봅니다.</strong> 3년 전에 산
              물량은 상당 부분 이미 팔렸을 텐데, 단순 평균은 어제 산 것과 똑같이 취급합니다.
            </li>
            <li>
              <strong className="text-white">순매도가 누적되면 계산이 깨집니다.</strong> 보유량을 0에서
              시작한다고 가정하면 순매도 구간에서 수량이 음수가 되어 단가를 낼 수 없습니다.
            </li>
          </ol>

          <h2 className="text-[17px] sm:text-[19px] font-semibold text-white mt-9 mb-3">
            회전율 가중 기준가격
          </h2>
          <p className="text-[15px] sm:text-[16px] text-[var(--text-secondary)] leading-[1.85]">
            이 사이트는 Grinblatt &amp; Han(2005)이 제시한{" "}
            <strong className="text-white">회전율 가중 기준가격</strong>을 투자자별로 적용합니다. 핵심
            발상은 단순합니다 — 오래전 매수분일수록 이미 팔렸을 가능성이 높으니, 아직 남아 있을 확률만큼만
            가중치를 줍니다.
          </p>

          <div className="mt-5 rounded-xl bg-white/[0.03] px-5 py-4">
            <p className="text-[14px] sm:text-[15px] text-[var(--text-secondary)] leading-[2.1] num">
              가중치 w<sub>n</sub> = B<sub>n</sub> × <span className="text-white">Π</span>(1 − s
              <sub>m</sub>)
              <br />
              평균단가 R = Σ w<sub>n</sub>P<sub>n</sub> ÷ Σ w<sub>n</sub>
            </p>
            <p className="text-[12px] sm:text-[13px] text-[var(--text-muted)] mt-3 leading-relaxed">
              B = 그날의 매수 수량 · P = 그날의 실제 매수 체결단가 · s = 그날의 이탈률(회전율)
            </p>
          </div>

          <p className="mt-5 text-[15px] sm:text-[16px] text-[var(--text-secondary)] leading-[1.85]">
            이탈률은 투자자별로 다르게 구합니다. <strong className="text-white">외국인</strong>은 보유
            주식 수가 공시되므로 매도량을 보유량으로 나눠 실제 값을 씁니다.{" "}
            <strong className="text-white">기관</strong>은 보유량 공시가 없어 시장 전체 회전율(거래량 ÷
            상장주식수)로 근사합니다.
          </p>
          <p className="mt-4 text-[15px] sm:text-[16px] text-[var(--text-secondary)] leading-[1.85]">
            매수 단가 P는 시장 평균가가 아니라{" "}
            <strong className="text-white">그 투자자가 실제로 체결한 단가</strong>를 씁니다. 한국거래소가
            투자자별 매수 대금과 매수 수량을 함께 공시하기 때문에 둘을 나누면 구할 수 있습니다.
          </p>

          <h2 className="text-[17px] sm:text-[19px] font-semibold text-white mt-9 mb-3">
            어떻게 보면 되나
          </h2>
          <p className="text-[15px] sm:text-[16px] text-[var(--text-secondary)] leading-[1.85]">
            종목 페이지에서 현재가와 평균단가를 나란히 보여줍니다. 둘의 거리가 그 투자자의 평가손익입니다.
            외국인과 기관의 평균단가가 서로 크게 다르면, 두 주체가 다른 구간에서 매수했다는 뜻입니다.
          </p>

          <h2 className="text-[17px] sm:text-[19px] font-semibold text-white mt-9 mb-3">
            자주 묻는 질문
          </h2>
          <div className="space-y-6">
            {FAQ.map((f) => (
              <div key={f.q}>
                <h3 className="text-[15px] sm:text-[16px] font-semibold text-white mb-1.5">{f.q}</h3>
                <p className="text-[14px] sm:text-[15px] text-[var(--text-secondary)] leading-[1.8]">
                  {f.a}
                </p>
              </div>
            ))}
          </div>

          <p className="mt-9 pt-5 border-t border-white/[0.04] text-[12px] sm:text-[13px] text-[var(--text-muted)] leading-relaxed">
            평균단가는 공시된 일별 매매 기록으로 계산한 추정치이며 실제 매입 단가와 다를 수 있습니다.
            출처: Grinblatt, M., &amp; Han, B. (2005). <em>Prospect theory, mental accounting, and
            momentum.</em> Journal of Financial Economics, 78(2), 311–339.
          </p>
        </article>

        <div className="bg-[var(--bg-card)] rounded-2xl px-5 py-4">
          <p className="text-[13px] sm:text-[14px] text-[var(--text-secondary)]">
            종목별 평균단가는{" "}
            <Link href="/stocks" className="text-[var(--accent-blue)] hover:underline">
              종목 목록
            </Link>
            에서 확인할 수 있습니다.
          </p>
        </div>
      </div>
    </>
  );
}
