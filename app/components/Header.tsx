"use client";

import { useState } from "react";
import Link from "next/link";
import SearchBar from "./SearchBar";

export default function Header() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header className="sticky top-0 z-40 border-b border-white/[0.06] bg-[#06080d]/90 backdrop-blur-xl">
      <div className="max-w-7xl mx-auto px-5 h-14 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link href="/" className="flex items-center gap-2 hover:opacity-80 transition">
            <svg width="28" height="28" viewBox="0 0 100 100" className="rounded-lg">
              <rect width="100" height="100" rx="22" fill="#2563eb"/>
              <path d="M57 27 L57 70 Q57 82 45 82 L35 82" stroke="white" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
              <circle cx="57" cy="23" r="5" fill="white"/>
            </svg>
            <span className="text-[15px] font-semibold tracking-tight text-white hidden sm:inline">
              JangsTrading
            </span>
          </Link>
          <SearchBar />
        </div>

        {/* 데스크톱 네비게이션 */}
        <nav className="hidden sm:flex items-center gap-1 text-[13px]">
          <Link href="/" className="px-3 py-1.5 rounded-lg text-[var(--text-secondary)] hover:text-white hover:bg-white/[0.06] transition">
            대시보드
          </Link>
          <Link href="/stocks" className="px-3 py-1.5 rounded-lg text-[var(--text-secondary)] hover:text-white hover:bg-white/[0.06] transition">
            종목
          </Link>
          <Link href="/sectors" className="px-3 py-1.5 rounded-lg text-[var(--text-secondary)] hover:text-white hover:bg-white/[0.06] transition">
            섹터
          </Link>
          <Link href="/reports" className="px-3 py-1.5 rounded-lg text-[var(--text-secondary)] hover:text-white hover:bg-white/[0.06] transition">
            AI 시황
          </Link>
          <a href="https://t.me/jangstrading" target="_blank" rel="noopener noreferrer"
            className="ml-1 px-2 py-1.5 rounded-lg text-[var(--text-muted)] hover:text-[#29B6F6] hover:bg-white/[0.06] transition"
            title="텔레그램 수급 알림"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
              <path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/>
            </svg>
          </a>
        </nav>

        {/* 모바일 햄버거 버튼 */}
        <button
          onClick={() => setMenuOpen(!menuOpen)}
          className="sm:hidden p-2 rounded-lg text-[var(--text-secondary)] hover:text-white hover:bg-white/[0.06] transition"
        >
          {menuOpen ? (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6L6 18M6 6l12 12"/>
            </svg>
          ) : (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 12h18M3 6h18M3 18h18"/>
            </svg>
          )}
        </button>
      </div>

      {/* 모바일 메뉴 */}
      {menuOpen && (
        <div className="sm:hidden border-t border-white/[0.06] bg-[#06080d]/95 backdrop-blur-xl">
          <nav className="max-w-7xl mx-auto px-5 py-3 flex flex-col gap-1">
            <Link href="/" onClick={() => setMenuOpen(false)}
              className="px-3 py-2.5 rounded-lg text-[var(--text-secondary)] hover:text-white hover:bg-white/[0.06] transition text-[14px]">
              대시보드
            </Link>
            <Link href="/stocks" onClick={() => setMenuOpen(false)}
              className="px-3 py-2.5 rounded-lg text-[var(--text-secondary)] hover:text-white hover:bg-white/[0.06] transition text-[14px]">
              종목 순매수
            </Link>
            <Link href="/sectors" onClick={() => setMenuOpen(false)}
              className="px-3 py-2.5 rounded-lg text-[var(--text-secondary)] hover:text-white hover:bg-white/[0.06] transition text-[14px]">
              섹터 순매수
            </Link>
            <Link href="/reports" onClick={() => setMenuOpen(false)}
              className="px-3 py-2.5 rounded-lg text-[var(--text-secondary)] hover:text-white hover:bg-white/[0.06] transition text-[14px]">
              AI 시황
            </Link>
            <div className="border-t border-white/[0.06] mt-1 pt-1">
              <a href="https://t.me/jangstrading" target="_blank" rel="noopener noreferrer"
                className="flex items-center gap-2 px-3 py-2.5 rounded-lg text-[#29B6F6] hover:bg-white/[0.06] transition text-[14px]">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z"/>
                </svg>
                텔레그램 수급 알림
              </a>
            </div>
          </nav>
        </div>
      )}
    </header>
  );
}
