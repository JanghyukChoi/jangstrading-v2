"use client";

import { useEffect, useState, use } from "react";
import Link from "next/link";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, Cell,
} from "recharts";

/* ── 타입 ─────────────────────────────────────── */
interface StockData {
  name: string;
  market: string;
  ticker: string;
  foreign: Record<string, number>;
  institution: Record<string, number>;
  combined: Record<string, number>;
}

/* ── 숫자 포맷 ────────────────────────────────── */
function fmt(n: number) {
  return n.toLocaleString("ko-KR", { maximumFractionDigits: 1 });
}
function CNum({ v, size = "text-sm" }: { v: number; size?: string }) {
  const cls = v > 0 ? "positive" : v < 0 ? "negative" : "text-[var(--text-secondary)]";
  return <span className={`num ${cls} ${size}`}>{v > 0 ? "+" : ""}{fmt(v)}</span>;
}

/* ── 수급 바 차트 ─────────────────────────────── */
function SupplyChart({ title, data, color }: { title: string; data: Record<string, number>; color: string }) {
  const periods = ["1d", "1w", "1m", "3m", "6m"];
  const labels: Record<string, string> = { "1d": "1일", "1w": "1주", "1m": "1개월", "3m": "3개월", "6m": "6개월" };

  const chartData = periods.map((p) => ({
    period: labels[p],
    value: Math.round(data[p]),
  }));

  const customTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload?.[0]) return null;
    const v = payload[0].value;
    return (
      <div className="bg-[#1c2128] border border-white/10 rounded-xl px-4 py-2.5 text-xs shadow-xl">
        <div className="text-[var(--text-secondary)] mb-1">{label}</div>
        <div className={`num font-medium ${v > 0 ? "text-[#f85149]" : "text-[#58a6ff]"}`}>
          {v > 0 ? "+" : ""}{fmt(v)} 백만원
        </div>
      </div>
    );
  };

  return (
    <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-6">
      <h3 className="text-sm font-medium text-[var(--text-secondary)] mb-5">{title}</h3>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={chartData} margin={{ top: 5, right: 5, bottom: 0, left: -15 }}>
          <XAxis dataKey="period" tick={{ fill: "#484f58", fontSize: 11 }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fill: "#484f58", fontSize: 10 }} axisLine={false} tickLine={false}
            tickFormatter={(v) => {
              if (Math.abs(v) >= 1000000) return `${(v / 1000000).toFixed(0)}M`;
              if (Math.abs(v) >= 1000) return `${(v / 1000).toFixed(0)}K`;
              return v;
            }}
          />
          <Tooltip content={customTooltip} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
          <ReferenceLine y={0} stroke="rgba(255,255,255,0.08)" />
          <Bar dataKey="value" radius={[4, 4, 0, 0]} maxBarSize={36}>
            {chartData.map((entry, i) => (
              <Cell key={i} fill={entry.value >= 0 ? "#f85149" : "#58a6ff"} fillOpacity={0.85} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/* ── 메인 ─────────────────────────────────────── */
export default function StockDetailPage({ params }: { params: Promise<{ ticker: string }> }) {
  const { ticker } = use(params);
  const [stockData, setStockData] = useState<StockData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/data/stock-rankings.json")
      .then((r) => r.json())
      .then((d) => {
        const found = d.data.find((s: StockData) => s.ticker === ticker);
        setStockData(found || null);
      })
      .finally(() => setLoading(false));
  }, [ticker]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-5 h-5 border-2 border-[var(--accent-blue)] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!stockData) {
    return (
      <div className="text-center py-20 text-[var(--text-muted)]">
        종목을 찾을 수 없습니다.
        <div className="mt-4">
          <Link href="/stocks" className="text-[var(--accent-blue)] hover:underline text-sm">← 종목 목록으로</Link>
        </div>
      </div>
    );
  }

  const periods = ["1d", "1w", "1m", "3m", "6m"] as const;
  const periodLabels: Record<string, string> = { "1d": "1일", "1w": "1주", "1m": "1개월", "3m": "3개월", "6m": "6개월" };
  const tvUrl = `https://www.tradingview.com/chart/?symbol=KRX%3A${stockData.ticker}`;

  return (
    <div className="space-y-5">
      {/* 헤더 */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <Link href="/stocks" className="text-[var(--text-muted)] hover:text-white transition text-sm">← 목록</Link>
          <div className="w-px h-4 bg-white/10" />
          <h1 className="text-2xl font-bold">{stockData.name}</h1>
          <span className={`text-[11px] px-2.5 py-1 rounded-lg font-medium ${
            stockData.market === "KOSPI" ? "bg-blue-500/10 text-blue-400" : "bg-purple-500/10 text-purple-400"
          }`}>{stockData.market}</span>
          <span className="text-[var(--text-muted)] text-sm num">{stockData.ticker}</span>
        </div>
        <a
          href={tvUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 px-4 py-2 bg-[#2962FF] text-white rounded-xl text-sm font-medium hover:brightness-110 transition"
        >
          <svg width="16" height="16" viewBox="0 0 36 28" fill="currentColor">
            <path d="M14 22H7V6h7V0H0v28h21v-7h-7v1zm22-22h-7v7h-8v7h8v7h7V0z"/>
          </svg>
          TradingView에서 차트 보기
        </a>
      </div>

      {/* 합산 요약 카드 */}
      <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-6">
        <h3 className="text-sm font-medium text-[var(--text-secondary)] mb-5">외국인 + 기관 합산 순매수 (백만원)</h3>
        <div className="grid grid-cols-5 gap-4">
          {periods.map((p) => {
            const v = stockData.combined[p];
            return (
              <div key={p} className={`text-center p-4 rounded-xl ${
                v > 0 ? "bg-red-500/[0.06]" : v < 0 ? "bg-blue-500/[0.06]" : "bg-white/[0.02]"
              }`}>
                <div className="text-[11px] text-[var(--text-muted)] mb-2">{periodLabels[p]}</div>
                <CNum v={v} size="text-lg" />
              </div>
            );
          })}
        </div>
      </div>

      {/* 외국인 / 기관 차트 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <SupplyChart title="외국인 순매수 추이" data={stockData.foreign} color="#f85149" />
        <SupplyChart title="기관 순매수 추이" data={stockData.institution} color="#58a6ff" />
      </div>

      {/* 합산 차트 */}
      <SupplyChart title="외국인 + 기관 합산 순매수" data={stockData.combined} color="#a371f7" />

      {/* 상세 테이블 */}
      <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-6">
        <h3 className="text-sm font-medium text-[var(--text-secondary)] mb-4">기간별 상세 (백만원)</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="text-[var(--text-muted)] text-[11px] border-b border-white/[0.06]">
                <th className="text-left py-3 font-normal">기간</th>
                <th className="text-right py-3 font-normal">외국인</th>
                <th className="text-right py-3 font-normal">기관</th>
                <th className="text-right py-3 font-normal font-medium">합계</th>
              </tr>
            </thead>
            <tbody>
              {periods.map((p) => (
                <tr key={p} className="border-t border-white/[0.03]">
                  <td className="py-3 text-[var(--text-secondary)]">{periodLabels[p]}</td>
                  <td className="py-3 text-right"><CNum v={stockData.foreign[p]} /></td>
                  <td className="py-3 text-right"><CNum v={stockData.institution[p]} /></td>
                  <td className="py-3 text-right font-medium"><CNum v={stockData.combined[p]} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
