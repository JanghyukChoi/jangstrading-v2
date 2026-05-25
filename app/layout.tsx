import type { Metadata } from "next";
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
    other: { "naver-site-verification": "279e4d3b77debaf01a1231d73f6965b7a0c3a66a" },
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
      </head>
      <body>
        <Header />
        <main className="max-w-7xl mx-auto px-5 py-6 pb-24 sm:pb-6">{children}</main>
        <BottomNav />
      </body>
    </html>
  );
}
