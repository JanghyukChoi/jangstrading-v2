/* 변동성 설명 글.

   숫자 출처: scripts/backtest_longfactors.py, backtest_lowrisk.py
   (10.3년 · 2,520영업일 · 유니버스 시총 1,000억+ 일평균 1,379종목 ·
    월 1회 리밸런스 110회 · 60영업일 보유 · 초과수익은 당일 유니버스
    동일가중 평균 차감 · Newey-West 중첩보정 · 종목 라벨 순열 200회 p=0.020)

   문구 원칙
     이 글을 읽는 사람은 통계를 모른다. "t값", "분위", "초과수익" 같은 말을
     쓰지 않는다. 대신 "4번 중 3번", "하루 평균 ±6%", "3개월 뒤" 로 쓴다.
     그리고 **틀릴 수 있다는 것을 숨기지 않는다** — 4번 중 1번은 반대였다.
*/

import type { Metadata } from "next";
import Link from "next/link";
import { BASE_URL, breadcrumb, jsonLdScript } from "@/app/lib/seo";

const SLUG = "변동성";
const PATH = `/guide/${SLUG}`;
const TITLE = "많이 흔들리는 종목은 정말 많이 벌까? — 10년 데이터로 확인";
const DESC =
  "주가가 크게 출렁이는 종목이 더 큰 수익을 줄까요? 한국 시장 10년 데이터로 확인한 결과, " +
  "가장 크게 흔들린 상위 10% 종목은 3개월 뒤 시장보다 평균 4.0% 낮았고 4번 중 3번 시장을 밑돌았습니다.";

export const META: Metadata = {
  title: TITLE,
  description: DESC,
  keywords: [
    "주식 변동성", "변동성 큰 종목", "급등주", "테마주 위험",
    "저변동성", "복권형 주식", "주가 변동폭", "변동성 뜻",
  ],
  alternates: { canonical: `${BASE_URL}${PATH}` },
  openGraph: {
    title: TITLE, description: DESC, type: "article",
    locale: "ko_KR", siteName: "JangsTrading", url: `${BASE_URL}${PATH}`,
  },
};

/* 10분위별 이후 60영업일 성과(유니버스 대비, %). backtest_lowrisk.py 실측.
   1 = 가장 잠잠, 10 = 가장 요동. */
const DECILES = [
  -0.60, -0.19, 0.50, 0.62, 1.09, 1.33, 1.29, 0.61, -0.66, -3.99,
];

const FAQ = [
  {
    q: "변동성이 크면 무조건 나쁜 건가요?",
    a: "아닙니다. 가장 크게 흔들린 10% 종목도 4번 중 1번은 시장보다 좋았습니다. 평균적으로 불리했다는 뜻이지, 개별 종목이 반드시 떨어진다는 뜻이 아닙니다.",
  },
  {
    q: "그럼 가장 잠잠한 종목을 사면 되나요?",
    a: "그것도 아닙니다. 가장 잠잠한 10% 종목은 오히려 시장보다 조금 낮았습니다. 성적이 가장 좋았던 것은 중간 정도로 움직이는 종목들이었습니다. 이 데이터가 말하는 것은 '조용한 걸 사라'가 아니라 '가장 요동치는 걸 피하라'입니다.",
  },
  {
    q: "변동성은 어떻게 계산하나요?",
    a: "지난 1년(252거래일) 동안 하루하루 주가가 얼마나 오르내렸는지를 재서, 그 흔들림의 크기를 숫자로 만듭니다. 화면에 표시되는 '하루 평균 ±0.0%'는 하루 변동폭의 평균입니다.",
  },
  {
    q: "왜 시가총액 1,000억 이상만 비교하나요?",
    a: "너무 작은 종목은 거래 자체가 드물어 주가가 튀는 것처럼 보이기 때문입니다. 검증도 같은 기준으로 했기 때문에 화면의 순위와 검증 결과가 같은 집단을 가리킵니다.",
  },
  {
    q: "앞으로도 똑같을까요?",
    a: "알 수 없습니다. 10년치 기록일 뿐입니다. 실제로 2020년에는 반대였습니다 — 코로나 이후 상승장에서는 크게 흔들리는 종목이 더 올랐습니다.",
  },
];

export default function VolatilityGuide() {
  const crumbs = breadcrumb([
    { name: "홈", url: "/" },
    { name: "변동성", url: PATH },
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
      "Bali, T. G., Cakici, N., & Whitelaw, R. F. (2011). Maxing out: Stocks as lotteries and the cross-section of expected returns. Journal of Financial Economics, 99(2), 427-446.",
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

  const worst = Math.min(...DECILES);
  const best = Math.max(...DECILES);
  const span = Math.max(Math.abs(worst), Math.abs(best));

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
            많이 흔들리는 종목은 정말 많이 벌까?
          </h1>

          {/* 한 줄 답. 스캔하는 사람이 여기서 끝낼 수 있어야 한다. */}
          <p className="mt-4 text-[15px] sm:text-[16px] text-[var(--text-secondary)] leading-[1.85]">
            지난 10년 한국 시장에서는 <strong className="text-white">반대였습니다.</strong> 가장 크게
            흔들린 10% 종목은 3개월 뒤 시장보다 평균 <strong className="text-white">4.0% 낮았고</strong>,{" "}
            <strong className="text-white">4번 중 3번</strong> 시장을 따라가지 못했습니다.
          </p>

          <h2 className="text-[17px] sm:text-[19px] font-semibold text-white mt-9 mb-3">
            &quot;흔들린다&quot;가 무슨 뜻인가요
          </h2>
          <p className="text-[15px] sm:text-[16px] text-[var(--text-secondary)] leading-[1.85]">
            하루에 주가가 얼마나 오르내리는지입니다. 지난 1년 동안의 하루 변동폭을 평균 내서 순서를
            매겼습니다. 같은 주식시장 안에서도 차이가 큽니다.
          </p>

          <div className="mt-5 rounded-xl bg-white/[0.03] px-5 py-4 space-y-3">
            <div className="flex items-baseline gap-3">
              <span className="text-[13px] text-[var(--text-muted)] w-24 shrink-0">조용한 쪽</span>
              <span className="text-[15px] sm:text-[16px] text-white num">하루 평균 ±0.4%</span>
              <span className="text-[13px] text-[var(--text-muted)]">인천도시가스</span>
            </div>
            <div className="flex items-baseline gap-3 pt-3 border-t border-white/[0.04]">
              <span className="text-[13px] text-[var(--text-muted)] w-24 shrink-0">요동치는 쪽</span>
              <span className="text-[15px] sm:text-[16px] text-white num">하루 평균 ±6.5%</span>
              <span className="text-[13px] text-[var(--text-muted)]">대한광통신</span>
            </div>
            <p className="text-[12px] text-[var(--text-muted)] pt-1">약 16배 차이가 납니다.</p>
          </div>

          <h2 className="text-[17px] sm:text-[19px] font-semibold text-white mt-9 mb-3">
            10개 그룹으로 나눠본 결과
          </h2>
          <p className="text-[15px] sm:text-[16px] text-[var(--text-secondary)] leading-[1.85]">
            매달 전 종목을 흔들림이 작은 순서로 10개 그룹으로 나눈 뒤, 3개월 뒤 성적을 시장 평균과
            비교했습니다. 10년 동안 110번 반복했습니다.
          </p>

          <div className="mt-5 rounded-xl bg-white/[0.03] px-4 sm:px-5 py-4">
            <div className="space-y-1.5">
              {DECILES.map((v, i) => {
                const isWorst = i === 9;
                const isBest = v === best;
                return (
                  <div key={i} className="flex items-center gap-2 sm:gap-3">
                    <span className="text-[11px] sm:text-[12px] text-[var(--text-muted)] w-[52px] sm:w-[62px] shrink-0 text-right">
                      {i === 0 ? "가장 조용" : i === 9 ? "가장 요동" : `${i + 1}번째`}
                    </span>
                    {/* 0을 가운데 두고 좌우로 뻗는 막대. 음수가 왼쪽이다. */}
                    <div className="flex-1 flex items-center min-w-0" aria-hidden="true">
                      <div className="w-1/2 flex justify-end">
                        {v < 0 && (
                          <div
                            className={`h-3.5 rounded-l ${isWorst ? "bg-[var(--accent-red)]" : "bg-[var(--accent-red)]/35"}`}
                            style={{ width: `${(Math.abs(v) / span) * 100}%` }}
                          />
                        )}
                      </div>
                      <div className="w-px h-4 bg-white/20 shrink-0" />
                      <div className="w-1/2">
                        {v > 0 && (
                          <div
                            className={`h-3.5 rounded-r ${isBest ? "bg-[var(--accent-green)]" : "bg-[var(--accent-green)]/35"}`}
                            style={{ width: `${(Math.abs(v) / span) * 100}%` }}
                          />
                        )}
                      </div>
                    </div>
                    <span
                      className={`text-[12px] sm:text-[13px] num w-[52px] shrink-0 text-right ${
                        v < 0 ? "negative" : "positive"
                      }`}
                    >
                      {v > 0 ? "+" : ""}
                      {v.toFixed(1)}%
                    </span>
                  </div>
                );
              })}
            </div>
            <p className="text-[12px] text-[var(--text-muted)] mt-4 leading-relaxed">
              3개월 뒤 성적을 시장 평균과 비교한 값입니다. 0보다 크면 시장보다 좋았다는 뜻입니다.
            </p>
          </div>

          <h2 className="text-[17px] sm:text-[19px] font-semibold text-white mt-9 mb-3">
            여기서 놓치면 안 되는 것
          </h2>
          <p className="text-[15px] sm:text-[16px] text-[var(--text-secondary)] leading-[1.85]">
            <strong className="text-white">조용한 종목이 제일 좋은 게 아닙니다.</strong> 가장 조용한
            10%는 오히려 시장보다 조금 낮았습니다(−0.6%). 성적이 가장 좋았던 것은 중간 정도로 움직이는
            종목들이었습니다(+1.3%).
          </p>
          <p className="mt-4 text-[15px] sm:text-[16px] text-[var(--text-secondary)] leading-[1.85]">
            즉 이 데이터가 말하는 것은 &quot;안전한 걸 사라&quot;가 아니라{" "}
            <strong className="text-white">&quot;제일 요동치는 10%를 피하라&quot;</strong>입니다. 나쁜
            성적이 맨 마지막 한 칸에 몰려 있습니다.
          </p>

          <h2 className="text-[17px] sm:text-[19px] font-semibold text-white mt-9 mb-3">
            왜 그럴까요 — 복권과 같습니다
          </h2>
          <p className="text-[15px] sm:text-[16px] text-[var(--text-secondary)] leading-[1.85]">
            1등 당첨금이 커지면 복권을 사는 사람이 늘어납니다. 사는 사람이 늘어도 당첨 확률은 그대로인데,
            줄은 길어집니다.
          </p>
          <p className="mt-4 text-[15px] sm:text-[16px] text-[var(--text-secondary)] leading-[1.85]">
            주식도 비슷합니다. &quot;이거 몇 배 간다&quot;는 기대가 붙은 종목에는 사람이 미리 몰립니다.
            몰리면 가격이 먼저 올라갑니다. 그래서{" "}
            <strong className="text-white">기대가 클수록 이미 비싸게 사는 상태</strong>가 됩니다. 학계에서는
            이것을 복권형 선호라고 부르고, 미국·유럽·아시아 대부분의 시장에서 같은 현상이 보고돼
            있습니다.
          </p>

          <h2 className="text-[17px] sm:text-[19px] font-semibold text-white mt-9 mb-3">
            한국 개인투자자에게 특히 중요한 이유
          </h2>
          <p className="text-[15px] sm:text-[16px] text-[var(--text-secondary)] leading-[1.85]">
            자본시장연구원이 개인 계좌 20만 개를 분석한 결과, 개인투자자가 하루에 사고파는 비율은
            시장 전체의 약 5배였습니다. 그리고 크게 출렁이는 종목에 투자한 신규 투자자의 누적 수익률은{" "}
            <strong className="text-white">−29.6%</strong>였습니다. 같은 기간 기존 투자자는 +8.4%였습니다.
          </p>
          <p className="mt-4 text-[15px] sm:text-[16px] text-[var(--text-secondary)] leading-[1.85]">
            많이 흔들리는 종목은 눈에 잘 띕니다. 급등락 순위에 오르고, 뉴스에 나오고, 커뮤니티에서
            이야기됩니다. 그래서 자연스럽게 손이 갑니다.
          </p>

          <h2 className="text-[17px] sm:text-[19px] font-semibold text-white mt-9 mb-3">
            이걸로 뭘 하면 되나요
          </h2>
          <p className="text-[15px] sm:text-[16px] text-[var(--text-secondary)] leading-[1.85]">
            종목을 <strong className="text-white">고르는</strong> 기준이 아니라{" "}
            <strong className="text-white">걸러보는</strong> 기준으로 쓰는 것이 맞습니다. 지금 들고 있는
            종목 중에 이 유형이 몇 개나 되는지 세어보는 정도가 적당합니다.
          </p>

          <h2 className="text-[17px] sm:text-[19px] font-semibold text-white mt-9 mb-3">
            믿지 말아야 할 부분
          </h2>
          <ul className="mt-2 space-y-3 text-[15px] sm:text-[16px] text-[var(--text-secondary)] leading-[1.75]">
            <li>
              <strong className="text-white">4번 중 1번은 반대였습니다.</strong> 가장 크게 흔들린 종목이
              시장을 이긴 경우도 25%입니다. 개별 종목의 미래를 맞히는 것이 아닙니다.
            </li>
            <li>
              <strong className="text-white">큰 회사에서는 나타나지 않습니다.</strong> 시가총액이 큰
              종목만 놓고 보면 이 차이가 사라집니다. 중소형 종목에서만 뚜렷했습니다.
            </li>
            <li>
              <strong className="text-white">2020년은 반대였습니다.</strong> 코로나 이후 상승장에서는
              크게 흔들리는 종목이 오히려 더 올랐습니다. 10년 중 3년이 그랬습니다.
            </li>
            <li>
              <strong className="text-white">10년은 긴 기간이 아닙니다.</strong> 앞으로도 같을 거라는
              보장은 없습니다.
            </li>
          </ul>

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
            2016년 2월 ~ 2026년 5월 한국거래소 상장 종목(시가총액 1,000억원 이상, 일평균 1,379종목)을
            매달 10개 그룹으로 나눠 3개월 뒤 성적을 비교했습니다. 상장폐지 종목을 포함합니다. 과거
            기록이며 미래 수익을 보장하지 않습니다. 본 내용은 투자 자문이 아닙니다. 참고: Bali, T. G.,
            Cakici, N., &amp; Whitelaw, R. F. (2011). <em>Maxing out: Stocks as lotteries and the
            cross-section of expected returns.</em> Journal of Financial Economics, 99(2), 427–446.
          </p>
        </article>

        <div className="bg-[var(--bg-card)] rounded-2xl px-5 py-4">
          <p className="text-[13px] sm:text-[14px] text-[var(--text-secondary)]">
            종목별 변동성은{" "}
            <Link href="/stocks" className="text-[var(--accent-blue)] hover:underline">
              종목 목록
            </Link>
            과 각 종목 페이지에서 확인할 수 있습니다.{" "}
            <Link href="/guide/평균단가" className="text-[var(--accent-blue)] hover:underline">
              평균단가란?
            </Link>
          </p>
        </div>
      </div>
    </>
  );
}
