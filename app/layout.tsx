import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "JangsTrading — 외국인·기관 수급 분석",
  description: "KOSPI/KOSDAQ 외국인·기관 투자자 순매수 데이터 분석 플랫폼",
};

function Header() {
  return (
    <header className="sticky top-0 z-40 border-b border-white/[0.06] bg-[#06080d]/90 backdrop-blur-xl">
      <div className="max-w-7xl mx-auto px-5 h-14 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2 hover:opacity-80 transition">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center text-white text-xs font-bold">
            J
          </div>
          <span className="text-[15px] font-semibold tracking-tight text-white">
            JangsTrading
          </span>
        </Link>

        <nav className="flex items-center gap-1 text-[13px]">
          <Link
            href="/"
            className="px-3 py-1.5 rounded-lg text-[var(--text-secondary)] hover:text-white hover:bg-white/[0.06] transition"
          >
            대시보드
          </Link>
          <Link
            href="/stocks"
            className="px-3 py-1.5 rounded-lg text-[var(--text-secondary)] hover:text-white hover:bg-white/[0.06] transition"
          >
            종목 순매수
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
