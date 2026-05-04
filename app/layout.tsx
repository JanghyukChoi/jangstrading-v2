import type { Metadata } from "next";
import Link from "next/link";
import SearchBar from "./components/SearchBar";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "JangsTrading — 외국인·기관 수급 분석",
    template: "%s | JangsTrading",
  },
  description: "KOSPI·KOSDAQ 외국인·기관 투자자 순매수 데이터를 실시간 분석합니다. 수급 전환 신호, 시총대비 비율, 추정 평균단가, 섹터·테마별 수급 현황을 무료로 제공합니다.",
  keywords: ["외국인 순매수", "기관 순매수", "수급 분석", "KOSPI", "KOSDAQ", "주식 수급", "투자자별 매매동향", "섹터 수급", "테마 수급"],
  openGraph: {
    title: "JangsTrading — 외국인·기관 수급 분석",
    description: "외국인·기관 투자자의 순매수 데이터를 실시간 분석하는 무료 플랫폼",
    type: "website",
    locale: "ko_KR",
    siteName: "JangsTrading",
  },
  robots: {
    index: true,
    follow: true,
  },
  verification: {
    // google: "구글서치콘솔_인증코드", // 나중에 추가
    other: { "naver-site-verification": "279e4d3b77debaf01a1231d73f6965b7a0c3a66a" },
  },
};

function Header() {
  return (
    <header className="sticky top-0 z-40 border-b border-white/[0.06] bg-[#06080d]/90 backdrop-blur-xl">
      <div className="max-w-7xl mx-auto px-5 h-14 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link href="/" className="flex items-center gap-2 hover:opacity-80 transition">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center text-white text-xs font-bold">
              J
            </div>
            <span className="text-[15px] font-semibold tracking-tight text-white hidden sm:inline">
              JangsTrading
            </span>
          </Link>
          <SearchBar />
        </div>

        <nav className="flex items-center gap-0.5 sm:gap-1 text-[11px] sm:text-[13px]">
          <Link
            href="/"
            className="px-1.5 sm:px-3 py-1.5 rounded-lg text-[var(--text-secondary)] hover:text-white hover:bg-white/[0.06] transition"
          >
            대시보드
          </Link>
          <Link
            href="/stocks"
            className="px-1.5 sm:px-3 py-1.5 rounded-lg text-[var(--text-secondary)] hover:text-white hover:bg-white/[0.06] transition"
          >
            종목
          </Link>
          <Link
            href="/sectors"
            className="px-1.5 sm:px-3 py-1.5 rounded-lg text-[var(--text-secondary)] hover:text-white hover:bg-white/[0.06] transition"
          >
            섹터
          </Link>
          <Link
            href="/reports"
            className="px-1.5 sm:px-3 py-1.5 rounded-lg text-[var(--text-secondary)] hover:text-white hover:bg-white/[0.06] transition"
          >
            AI 시황
          </Link>
        </nav>
      </div>
    </header>
  );
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <head>
        <link
          rel="stylesheet"
          href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css"
        />
      </head>
      <body>
        <Header />
        <main className="max-w-7xl mx-auto px-5 py-6">{children}</main>
      </body>
    </html>
  );
}
