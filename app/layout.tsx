import type { Metadata } from "next";
import Script from "next/script";
import { Analytics } from "@vercel/analytics/next";
import { SpeedInsights } from "@vercel/speed-insights/next";
import Header from "./components/Header";
import BottomNav from "./components/BottomNav";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "JangsTrading — 외국인·기관 수급 분석",
    template: "%s | JangsTrading",
  },
  description: "KOSPI·KOSDAQ 외국인·기관 투자자 순매수 데이터를 실시간 분석합니다. 수급 전환 신호, 시총대비 비율, 추정 평균단가, 섹터·테마별 수급 현황을 무료로 제공합니다.",
  keywords: ["외국인 순매수", "기관 순매수", "수급 분석", "KOSPI", "KOSDAQ", "주식 수급", "투자자별 매매동향", "섹터 수급", "테마 수급"],
  alternates: {
    canonical: "https://www.jangstrading.com",
  },
  openGraph: {
    title: "JangsTrading — 외국인·기관 수급 분석",
    description: "외국인·기관 투자자의 순매수 데이터를 실시간 분석하는 무료 플랫폼",
    type: "website",
    locale: "ko_KR",
    siteName: "JangsTrading",
    images: [{ url: "https://www.jangstrading.com/og-image.png", width: 1200, height: 630 }],
  },
  robots: {
    index: true,
    follow: true,
  },
  verification: {
    other: {
      "naver-site-verification": "279e4d3b77debaf01a1231d73f6965b7a0c3a66a",
      "google-adsense-account": "ca-pub-3284130465723516",
    },
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <head>
        <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
        <link
          rel="stylesheet"
          href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css"
        />
        <Script
          async
          src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-3284130465723516"
          crossOrigin="anonymous"
          strategy="beforeInteractive"
        />
      </head>
      <body>
        <Header />
        <main className="max-w-7xl mx-auto px-5 py-6 pb-24 sm:pb-6">{children}</main>
        <footer className="max-w-7xl mx-auto px-5 pb-28 sm:pb-10 mt-8">
          <div className="border-t border-white/[0.06] pt-6 text-[11px] text-[var(--text-muted)] leading-relaxed space-y-1.5">
            <p className="font-medium text-[var(--text-secondary)]">투자 유의사항</p>
            <p>본 서비스는 투자 자문이 아닙니다. 표시된 정보는 한국거래소(KRX) 공시 데이터를 기반으로 한 사실 정보이며, 종목 추천이 아닌 분석 도구입니다.</p>
            <p>투자 판단과 그에 따른 손익의 책임은 사용자 본인에게 있습니다. 과거 데이터 및 백테스트 결과는 미래 수익을 보장하지 않습니다.</p>
            <p className="pt-2 text-[var(--text-muted)] opacity-70">© JangsTrading. 모든 데이터는 한국거래소(KRX) 공시 자료를 기반으로 합니다.</p>
          </div>
        </footer>
        <BottomNav />
        <Analytics />
        <SpeedInsights />
      </body>
    </html>
  );
}
