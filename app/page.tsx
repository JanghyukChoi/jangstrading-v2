"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, ReferenceLine,
} from "recharts";

/* ── 타입 ─────────────────────────────────────── */
interface Flow { foreign: number; institution: number; individual: number }
interface MarketData {
  index: number | null;
  change: number | null;
  flow: Record<string, Flow>;
}
interface StockRanking {
  name: string;
  market: string;
  foreign: Record<string, number>;
  institution: Record<string, number>;
  combined: Record<string, number>;
}

/* ── 유틸 ─────────────────────────────────────── */
function fmt(n: number | null | undefined, d = 0) {
  if (n == null) return "-";
  return n.toLocaleString("ko-KR", { minimumFractionDigits: d, maximumFractionDigits: d });
}
function CNum({ v, suffix = "" }: { v: number | null; suffix?: string }) {
  if (v == null) return <span className="num text-[var(--text-muted)]">-</span>;
  const cls = v > 0 ? "positive" : v < 0 ? "negative" : "text-[var(--text-secondary)]";
  return <span className={`num ${cls}`}>{v > 0 ? "+" : ""}{fmt(v, 1)}{suffix}</span>;
}

/* ── 인덱스 카드 ──────────────────────────────── */
function IndexCard({ name, data }: { name: string; data: MarketData | null }) {
  if (!data) return null;
  const f = data.flow?.["1d"];
  return (
    <div className="flex-1 min-w-[280px] bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-6">
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm text-[var(--text-secondary)]">{name}</span>
        {data.change != null && <CNum v={data.change} suffix="%" />}
      </div>
      <div className="text-3xl font-bold num mb-5 tracking-tight">{fmt(data.index, 2)}</div>
      {f && (
        <div className="grid grid-cols-3 gap-4">
          {([["외국인", f.foreign], ["기관", f.institution], ["개인", f.individual]] as const).map(
            ([label, val]) => (
              <div key={label} className="text-center">
                <div className="text-[11px] text-[var(--text-muted)] mb-1">{label}</div>
                <CNum v={val as number} />
              </div>
            )
          )}
        </div>
      )}
    </div>
  );
}

/* ── 자금흐름 차트 ────────────────────────────── */
function FlowChart({ title, data }: { title: string; data: MarketData | null }) {
  if (!data?.flow) return null;
  const labels: Record<string, string> = { "1d": "1일", "1w": "1주", "1m": "1개월", "3m": "3개월", "6m": "6개월" };
  const periods = ["1d", "1w", "1m", "3m", "6m"];

  const chartData = periods
    .filter((p) => data.flow[p])
    .map((p) => ({
      period: labels[p],
      foreign: Math.round(data.flow[p].foreign),
      institution: Math.round(data.flow[p].institution),
      individual: Math.round(data.flow[p].individual),
    }));

  const customTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload) return null;
    return (
      <div className="bg-[#1c2128] border border-white/10 rounded-xl px-4 py-3 text-xs shadow-xl">
        <div className="text-[var(--text-secondary)] mb-2">{label}</div>
        {payload.map((p: any) => (
          <div key={p.dataKey} className="flex justify-between gap-6 mb-0.5">
            <span style={{ color: p.fill }}>{p.dataKey === "foreign" ? "외국인" : p.dataKey === "institution" ? "기관" : "개인"}</span>
            <span className="num text-white">{fmt(p.value)}</span>
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-6">
      <h3 className="text-sm font-medium text-[var(--text-secondary)] mb-5">{title}</h3>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={chartData} barGap={2} margin={{ top: 0, right: 0, bottom: 0, left: -10 }}>
          <XAxis
            dataKey="period"
            tick={{ fill: "#484f58", fontSize: 11 }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: "#484f58", fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v) => `${(v / 1000000).toFixed(0)}M`}
          />
          <Tooltip content={customTooltip} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
          <ReferenceLine y={0} stroke="rgba(255,255,255,0.06)" />
          <Bar dataKey="foreign" fill="#f85149" radius={[3, 3, 0, 0]} maxBarSize={24} />
          <Bar dataKey="institution" fill="#58a6ff" radius={[3, 3, 0, 0]} maxBarSize={24} />
          <Bar dataKey="individual" fill="#8b949e" radius={[3, 3, 0, 0]} maxBarSize={24} />
        </BarChart>
      </ResponsiveContainer>
      <div className="flex justify-center gap-5 mt-3 text-[11px] text-[var(--text-secondary)]">
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm bg-[#f85149]" />외국인</span>
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm bg-[#58a6ff]" />기관</span>
        <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm bg-[#8b949e]" />개인</span>
      </div>
    </div>
  );
}

/* ── 순매수 바 ─────────────────────────────────── */
function PurchaseBar({ value, max }: { value: number; max: number }) {
  const pct = max === 0 ? 0 : Math.min(Math.abs(value) / max * 100, 100);
  const bg = value >= 0
    ? "bg-gradient-to-r from-red-500/80 to-red-500/20"
    : "bg-gradient-to-l from-blue-400/80 to-blue-400/20";
  return (
    <div className="w-16 h-[5px] rounded-full bg-white/[0.04] overflow-hidden">
      <div className={`h-full rounded-full ${bg}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

/* ── TOP 10 테이블 ────────────────────────────── */
function TopTable({ title, stocks, type }: { title: string; stocks: StockRanking[]; type: "buy" | "sell" }) {
  const sorted = [...stocks]
    .sort((a, b) => type === "buy" ? b.combined["1m"] - a.combined["1m"] : a.combined["1m"] - b.combined["1m"])
    .slice(0, 10);
  const maxVal = Math.max(...sorted.map((s) => Math.abs(s.combined["1m"])), 1);

  return (
    <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-6">
      <h3 className="text-sm font-medium text-[var(--text-secondary)] mb-4">{title}</h3>
      <table className="w-full text-[13px]">
        <thead>
          <tr className="text-[var(--text-muted)] text-[11px]">
            <th className="text-left py-2 font-normal w-7">#</th>
            <th className="text-left py-2 font-normal">종목</th>
            <th className="text-right py-2 font-normal">외국인</th>
            <th className="text-right py-2 font-normal">기관</th>
            <th className="text-right py-2 font-normal">합계</th>
            <th className="py-2 w-16"></th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((s, i) => (
            <tr key={s.name} className="border-t border-white/[0.04] hover:bg-white/[0.02] transition">
              <td className="py-2.5 text-[var(--text-muted)] num text-xs">{i + 1}</td>
              <td className="py-2.5">
                <span className="text-white font-medium">{s.name}</span>
                <span className={`ml-1.5 text-[10px] px-1.5 py-0.5 rounded ${
                  s.market === "KOSPI" ? "bg-blue-500/10 text-blue-400" : "bg-purple-500/10 text-purple-400"
                }`}>{s.market}</span>
              </td>
              <td className="py-2.5 text-right text-xs"><CNum v={s.foreign["1m"]} /></td>
              <td className="py-2.5 text-right text-xs"><CNum v={s.institution["1m"]} /></td>
              <td className="py-2.5 text-right font-medium"><CNum v={s.combined["1m"]} /></td>
              <td className="py-2.5 pl-3"><PurchaseBar value={s.combined["1m"]} max={maxVal} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── 메인 ─────────────────────────────────────── */
export default function Dashboard() {
  const [market, setMarket] = useState<Record<string, MarketData> | null>(null);
  const [stocks, setStocks] = useState<StockRanking[]>([]);
  const [meta, setMeta] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch("/data/market-overview.json").then((r) => r.json()),
      fetch("/data/stock-rankings.json").then((r) => r.json()),
      fetch("/data/meta.json").then((r) => r.json()),
    ])
      .then(([m, s, mt]) => { setMarket(m.data); setStocks(s.data); setMeta(mt); })
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
    <div className="space-y-5">
      {meta && (
        <p className="text-[11px] text-[var(--text-muted)]">
          기준일 {meta.business_date} · {new Date(meta.last_updated).toLocaleString("ko-KR")} 업데이트
        </p>
      )}

      {/* 지수 */}
      <div className="flex flex-col sm:flex-row gap-4">
        <IndexCard name="KOSPI" data={market?.KOSPI ?? null} />
        <IndexCard name="KOSDAQ" data={market?.KOSDAQ ?? null} />
      </div>

      {/* 자금흐름 차트 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <FlowChart title="KOSPI 투자자별 자금흐름" data={market?.KOSPI ?? null} />
        <FlowChart title="KOSDAQ 투자자별 자금흐름" data={market?.KOSDAQ ?? null} />
      </div>

      {/* TOP 10 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <TopTable title="1개월 순매수 TOP 10" stocks={stocks} type="buy" />
        <TopTable title="1개월 순매도 TOP 10" stocks={stocks} type="sell" />
      </div>

      <div className="text-center pt-2">
        <Link
          href="/stocks"
          className="inline-flex items-center gap-2 px-6 py-2.5 bg-[var(--accent-blue)] text-white rounded-xl text-sm font-medium hover:brightness-110 transition"
        >
          전체 종목 순매수 보기
          <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M6.22 3.22a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06l-4.25 4.25a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042L9.94 8 6.22 4.28a.75.75 0 0 1 0-1.06Z"/></svg>
        </Link>
      </div>
    </div>
  );
}
