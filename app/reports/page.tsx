"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

export const dynamic = "force-static";

interface Report {
  date: string;
  title: string;
  body: string;
  news_count?: number;
}

export default function ReportsPage() {
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/data/reports/index.json")
      .then((r) => r.json())
      .then(async (idx: { date: string; title: string }[]) => {
        const full = await Promise.all(
          idx.map((item) =>
            fetch(`/data/reports/${item.date}.json`).then((r) => r.json()).catch(() => null)
          )
        );
        setReports(full.filter(Boolean) as Report[]);
      })
      .catch(() => setReports([]))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-5 h-5 border-2 border-[var(--accent-blue)] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const latest = reports[0];
  const rest = reports.slice(1);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg sm:text-xl font-semibold tracking-tight">AI 시황 분석</h1>
        <p className="text-[11px] text-[var(--text-muted)] mt-1">매일 수급 데이터 + 뉴스 기반 자동 생성</p>
      </div>

      {reports.length === 0 ? (
        <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-8 text-center">
          <p className="text-[var(--text-muted)] text-sm">아직 생성된 리포트가 없습니다.</p>
          <p className="text-[var(--text-muted)] text-xs mt-1">평일 오후 5시경 자동 생성됩니다.</p>
        </div>
      ) : (
        <>
          {/* HERO: 최신 시황 */}
          {latest && (
            <Link
              href={`/reports/${latest.date}`}
              className="block bg-gradient-to-br from-[var(--bg-card)] to-[#161b22] border border-white/[0.08] rounded-2xl p-5 sm:p-7 hover:border-white/[0.18] transition group"
            >
              <div className="flex items-center gap-2 mb-3">
                <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-[var(--accent-blue)]/20 text-[var(--accent-blue)] font-medium">AI 시황</span>
                <span className="text-[10px] text-[var(--text-muted)] num">{latest.date}</span>
                <span className="text-[9px] px-1.5 py-0.5 rounded-md bg-amber-500/15 text-amber-400 font-medium">최신</span>
              </div>
              <h2 className="text-[17px] sm:text-[21px] font-semibold text-white leading-snug mb-2.5 tracking-tight">
                {latest.title}
              </h2>
              {latest.body && (
                <p className="text-[12px] sm:text-[13px] text-[var(--text-secondary)] leading-relaxed line-clamp-2">
                  {latest.body}
                </p>
              )}
              <div className="flex items-center gap-1 mt-4 text-[12px] text-[var(--accent-blue)] group-hover:gap-2 transition-all">
                <span>자세히 보기</span>
                <svg width="11" height="11" viewBox="0 0 16 16" fill="currentColor"><path d="M6.22 3.22a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06l-4.25 4.25a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042L9.94 8 6.22 4.28a.75.75 0 0 1 0-1.06Z"/></svg>
              </div>
            </Link>
          )}

          {/* 이전 시황 리스트 */}
          {rest.length > 0 && (
            <div>
              <h3 className="text-[12px] text-[var(--text-muted)] mt-6 mb-3">이전 시황</h3>
              <div className="space-y-2">
                {rest.map((r) => (
                  <Link
                    key={r.date}
                    href={`/reports/${r.date}`}
                    className="flex items-start gap-3 bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl px-5 py-4 hover:bg-white/[0.02] transition"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className="text-[11px] text-[var(--text-muted)] num">{r.date}</span>
                      </div>
                      <h4 className="text-[14px] sm:text-[15px] text-white font-medium leading-snug mb-1.5">{r.title}</h4>
                      {r.body && (
                        <p className="text-[12px] text-[var(--text-secondary)] leading-relaxed line-clamp-1">{r.body}</p>
                      )}
                    </div>
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" className="text-[var(--text-muted)] shrink-0 mt-1">
                      <path d="M6.22 3.22a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06l-4.25 4.25a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042L9.94 8 6.22 4.28a.75.75 0 0 1 0-1.06Z"/>
                    </svg>
                  </Link>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
