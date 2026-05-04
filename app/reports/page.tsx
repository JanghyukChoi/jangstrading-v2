"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

interface ReportIndex {
  date: string;
  title: string;
}

export default function ReportsPage() {
  const [reports, setReports] = useState<ReportIndex[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/data/reports/index.json")
      .then((r) => r.json())
      .then((d) => setReports(d))
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
        <div className="space-y-2">
          {reports.map((r, i) => (
            <Link
              key={r.date}
              href={`/reports/${r.date}`}
              className="flex items-center justify-between bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl px-5 py-4 hover:bg-white/[0.02] transition"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-[11px] text-[var(--text-muted)] num">{r.date}</span>
                  {i === 0 && (
                    <span className="text-[9px] px-1.5 py-0.5 rounded-md bg-[var(--accent-blue)]/20 text-[var(--accent-blue)] font-medium">최신</span>
                  )}
                </div>
                <h2 className="text-[14px] sm:text-[15px] text-white font-medium truncate">{r.title}</h2>
              </div>
              <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" className="text-[var(--text-muted)] shrink-0 ml-3">
                <path d="M6.22 3.22a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06l-4.25 4.25a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042L9.94 8 6.22 4.28a.75.75 0 0 1 0-1.06Z"/>
              </svg>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
