"use client";

import { useEffect, useState, use } from "react";
import { useRouter } from "next/navigation";

interface Report {
  date: string;
  title: string;
  body: string;
  generated_at: string;
  news_count: number;
}

export default function ReportDetailPage({ params }: { params: Promise<{ date: string }> }) {
  const { date } = use(params);
  const router = useRouter();
  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/data/reports/${date}.json`)
      .then((r) => r.json())
      .then((d) => setReport(d))
      .catch(() => setReport(null))
      .finally(() => setLoading(false));
  }, [date]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-5 h-5 border-2 border-[var(--accent-blue)] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!report) {
    return (
      <div className="text-center py-16">
        <p className="text-[var(--text-muted)]">리포트를 찾을 수 없습니다.</p>
        <button onClick={() => router.back()} className="text-[var(--accent-blue)] mt-2 text-sm hover:underline">← 돌아가기</button>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto space-y-4">
      {/* 헤더 */}
      <div className="flex items-center gap-3">
        <button onClick={() => router.back()} className="text-[var(--text-muted)] hover:text-white transition text-sm">
          ← 시황 목록
        </button>
      </div>

      <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-5 sm:p-8">
        {/* 메타 */}
        <div className="flex items-center gap-2 mb-3">
          <span className="text-[11px] text-[var(--text-muted)] num">{report.date}</span>
          <span className="text-[10px] text-[var(--text-muted)]">·</span>
          <span className="text-[10px] text-[var(--text-muted)]">뉴스 {report.news_count}건 참고</span>
          <span className="text-[10px] text-[var(--text-muted)]">·</span>
          <span className="text-[10px] text-[var(--text-muted)]">AI 자동 생성</span>
        </div>

        {/* 제목 */}
        <h1 className="text-xl sm:text-2xl font-bold text-white leading-snug mb-6">{report.title}</h1>

        {/* 본문 */}
        <div className="text-[14px] sm:text-[15px] text-[var(--text-secondary)] leading-[1.85] whitespace-pre-line">
          {report.body}
        </div>

        {/* 면책 */}
        <div className="mt-8 pt-4 border-t border-white/[0.04]">
          <p className="text-[10px] text-[var(--text-muted)] leading-relaxed">
            본 시황 분석은 AI가 수급 데이터와 뉴스를 기반으로 자동 생성한 참고 자료이며, 투자 권유나 추천이 아닙니다.
            투자 판단의 책임은 투자자 본인에게 있습니다.
          </p>
        </div>
      </div>
    </div>
  );
}
