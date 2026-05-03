"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine,
  PieChart, Pie, Cell,
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
  ticker?: string;
  market_cap?: number | null;
  price_change?: Record<string, number>;
  foreign: Record<string, number>;
  institution: Record<string, number>;
  combined: Record<string, number>;
}

/* ── 유틸 ─────────────────────────────────────── */
function fmt(n: number | null | undefined, d = 0) {
  if (n == null) return "-";
  return n.toLocaleString("ko-KR", { minimumFractionDigits: d, maximumFractionDigits: d });
}
// n = 백만원 단위 → 원 단위로 변환하여 표시
function fmtUnit(n: number) {
  const won = n * 1_000_000;
  const abs = Math.abs(won);
  const sign = won > 0 ? "+" : "";
  if (abs >= 1_000_000_000_000) return `${sign}${(won / 1_000_000_000_000).toFixed(1)}조원`;
  if (abs >= 100_000_000) return `${sign}${Math.round(won / 100_000_000).toLocaleString()}억원`;
  if (abs >= 10_000) return `${sign}${Math.round(won / 10_000).toLocaleString()}만원`;
  return `${sign}${Math.round(won).toLocaleString()}원`;
}
function CNum({ v, suffix = "" }: { v: number | null; suffix?: string }) {
  if (v == null) return <span className="num text-[var(--text-muted)]">-</span>;
  const cls = v > 0 ? "positive" : v < 0 ? "negative" : "text-[var(--text-secondary)]";
  return <span className={`num ${cls}`}>{fmtUnit(v)}{suffix}</span>;
}

/* ── 외국인 vs 기관 방향 일치 ─────────────────── */
function ConsensusChart({ stocks, period = "1m" }: { stocks: StockRanking[]; period?: string }) {
  // 시총 1000억 이상만
  const filtered = stocks.filter((s) => (s.market_cap ?? 0) >= 1000);

  let bothBuy = 0, bothSell = 0, mixed = 0;
  for (const s of filtered) {
    const f = s.foreign[period] ?? 0;
    const i = s.institution[period] ?? 0;
    if (f > 0 && i > 0) bothBuy++;
    else if (f < 0 && i < 0) bothSell++;
    else mixed++;
  }

  const data = [
    { name: "동시 순매수", value: bothBuy, color: "#f85149" },
    { name: "엇갈림", value: mixed, color: "#484f58" },
    { name: "동시 순매도", value: bothSell, color: "#58a6ff" },
  ];

  const total = bothBuy + bothSell + mixed;

  const customTooltip = ({ active, payload }: any) => {
    if (!active || !payload?.[0]) return null;
    const d = payload[0].payload;
    const pct = total > 0 ? ((d.value / total) * 100).toFixed(1) : "0";
    return (
      <div className="bg-[#1c2128] border border-white/10 rounded-xl px-3 py-2 text-[11px] shadow-xl">
        <span style={{ color: d.color }}>{d.name}</span>
        <span className="text-white ml-2 num">{d.value}종목 ({pct}%)</span>
      </div>
    );
  };

  return (
    <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-4 sm:p-6">
      <h3 className="text-xs sm:text-sm font-medium text-[var(--text-secondary)] mb-1">외국인 vs 기관 방향 일치</h3>
      <p className="text-[10px] text-[var(--text-muted)] mb-4">1개월 기준 · 시총 1천억 이상</p>

      <div className="flex items-center gap-6">
        {/* 도넛 차트 */}
        <div className="w-32 h-32 sm:w-40 sm:h-40 shrink-0">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data}
                cx="50%"
                cy="50%"
                innerRadius="55%"
                outerRadius="85%"
                paddingAngle={3}
                dataKey="value"
                stroke="none"
              >
                {data.map((d, i) => (
                  <Cell key={i} fill={d.color} />
                ))}
              </Pie>
              <Tooltip content={customTooltip} />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* 범례 */}
        <div className="flex-1 space-y-3">
          {data.map((d) => {
            const pct = total > 0 ? ((d.value / total) * 100).toFixed(1) : "0";
            return (
              <div key={d.name} className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: d.color }} />
                  <span className="text-[12px] sm:text-[13px] text-[var(--text-secondary)]">{d.name}</span>
                </div>
                <div className="text-right">
                  <span className="text-[13px] sm:text-sm text-white font-semibold num">{d.value}</span>
                  <span className="text-[11px] text-[var(--text-muted)] ml-1">({pct}%)</span>
                </div>
              </div>
            );
          })}
          <div className="pt-2 border-t border-white/[0.04]">
            <div className="flex items-center justify-between text-[11px] text-[var(--text-muted)]">
              <span>전체</span>
              <span className="num">{total}종목</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── 인덱스 카드 ──────────────────────────────── */
function IndexCard({ name, data }: { name: string; data: MarketData | null }) {
  if (!data) return null;
  const f = data.flow?.["1d"];
  return (
    <div className="flex-1 min-w-0 bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-4 sm:p-6">
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm text-[var(--text-secondary)]">{name}</span>
        {data.change != null && (
          <span className={`num text-sm ${data.change > 0 ? "positive" : data.change < 0 ? "negative" : ""}`}>
            {data.change > 0 ? "+" : ""}{data.change.toFixed(2)}%
          </span>
        )}
      </div>
      <div className="text-2xl sm:text-3xl font-bold num mb-4 tracking-tight">{fmt(data.index, 2)}</div>
      {f && (
        <div className="grid grid-cols-3 gap-2">
          {([["외국인", f.foreign], ["기관", f.institution], ["개인", f.individual]] as const).map(
            ([label, val]) => (
              <div key={label} className="text-center">
                <div className="text-[10px] text-[var(--text-muted)] mb-1">{label}</div>
                <div className="text-[11px] sm:text-xs"><CNum v={val as number} /></div>
              </div>
            )
          )}
        </div>
      )}
      <div className="text-[9px] text-[var(--text-muted)] mt-2 text-center">당일 순매수</div>
    </div>
  );
}

/* ── 자금흐름 차트 ────────────────────────────── */
function FlowChart({ title, data }: { title: string; data: MarketData | null }) {
  if (!data?.flow) return null;
  const labels: Record<string, string> = { "1d": "1일", "1w": "1주", "1m": "1개월", "3m": "3개월", "6m": "6개월" };
  const chartData = ["1d", "1w", "1m", "3m", "6m"]
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
      <div className="bg-[#1c2128] border border-white/10 rounded-xl px-3 py-2 text-[11px] shadow-xl">
        <div className="text-[var(--text-secondary)] mb-1.5">{label}</div>
        {payload.map((p: any) => (
          <div key={p.dataKey} className="flex justify-between gap-4 mb-0.5">
            <span style={{ color: p.fill }}>{p.dataKey === "foreign" ? "외국인" : p.dataKey === "institution" ? "기관" : "개인"}</span>
            <span className="num text-white">{fmtUnit(p.value)}</span>
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-4 sm:p-6">
      <h3 className="text-xs sm:text-sm font-medium text-[var(--text-secondary)]">{title}</h3>
      <p className="text-[10px] text-[var(--text-muted)] mb-3">기간별 투자자 순매수 금액</p>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={chartData} barGap={2} margin={{ top: 0, right: 0, bottom: 0, left: -20 }}>
          <XAxis dataKey="period" tick={{ fill: "#484f58", fontSize: 10 }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fill: "#484f58", fontSize: 9 }} axisLine={false} tickLine={false}
            tickFormatter={(v) => fmtUnit(v)} />
          <Tooltip content={customTooltip} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
          <ReferenceLine y={0} stroke="rgba(255,255,255,0.06)" />
          <Bar dataKey="foreign" fill="#f85149" radius={[3, 3, 0, 0]} maxBarSize={20} />
          <Bar dataKey="institution" fill="#58a6ff" radius={[3, 3, 0, 0]} maxBarSize={20} />
          <Bar dataKey="individual" fill="#8b949e" radius={[3, 3, 0, 0]} maxBarSize={20} />
        </BarChart>
      </ResponsiveContainer>
      <div className="flex justify-center gap-4 mt-2 text-[10px] text-[var(--text-secondary)]">
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-[#f85149]" />외국인</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-[#58a6ff]" />기관</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-[#8b949e]" />개인</span>
      </div>
    </div>
  );
}

/* ── 수급 집중도 ──────────────────────────────── */
function ConcentrationCard({ title, stocks, investorKey, color }: {
  title: string;
  stocks: StockRanking[];
  investorKey: "foreign" | "institution";
  color: string;
}) {
  // 순매수 양수인 종목만 대상
  const buyers = stocks
    .filter((s) => s[investorKey]["1m"] > 0)
    .sort((a, b) => b[investorKey]["1m"] - a[investorKey]["1m"]);

  const totalBuy = buyers.reduce((sum, s) => sum + s[investorKey]["1m"], 0);
  const top5 = buyers.slice(0, 5);
  const top5Sum = top5.reduce((sum, s) => sum + s[investorKey]["1m"], 0);
  const pct = totalBuy > 0 ? Math.round(top5Sum / totalBuy * 1000) / 10 : 0;

  const badgeLabel = pct >= 70 ? "집중 매수" : pct >= 40 ? "보통" : "분산 매수";
  const badgeColor = pct >= 70
    ? "bg-red-500/[0.12] text-[#f85149]"
    : pct >= 40
    ? "bg-amber-500/[0.12] text-[#d29922]"
    : "bg-green-500/[0.12] text-[#3fb950]";

  return (
    <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-4 sm:p-6 flex-1 min-w-0">
      <p className="text-[11px] sm:text-xs text-[var(--text-secondary)] mb-1">{title}</p>
      <div className="flex items-baseline gap-2 mb-1">
        <span className="text-2xl sm:text-3xl font-semibold num">{pct}%</span>
        <span className={`text-[10px] sm:text-[11px] px-2 py-0.5 rounded-md font-medium ${badgeColor}`}>{badgeLabel}</span>
      </div>
      <p className="text-[10px] text-[var(--text-muted)] mb-3">상위 5종목이 전체 순매수의 {pct}%</p>

      {/* 바 */}
      <div className="h-1.5 rounded-full bg-white/[0.06] overflow-hidden flex mb-3">
        <div className="h-full rounded-l-full" style={{ width: `${pct}%`, background: color }} />
        <div className="h-full" style={{ width: `${100 - pct}%`, background: "rgba(255,255,255,0.06)" }} />
      </div>

      {/* 상위 5 종목 */}
      <div className="space-y-0">
        {top5.map((s, i) => {
          const stockPct = totalBuy > 0 ? (s[investorKey]["1m"] / totalBuy * 100).toFixed(1) : "0";
          return (
            <div key={s.name} className="flex items-center justify-between py-1.5 border-t border-white/[0.03] first:border-0">
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-[var(--text-muted)] num text-[10px] w-4 shrink-0">{i + 1}</span>
                {s.ticker ? (
                  <Link href={`/stocks/${s.ticker}`} className="text-[12px] sm:text-[13px] text-white font-medium hover:text-[var(--accent-blue)] transition truncate">
                    {s.name}
                  </Link>
                ) : (
                  <span className="text-[12px] sm:text-[13px] text-white font-medium truncate">{s.name}</span>
                )}
                <span className="text-[10px] text-[var(--text-muted)] shrink-0">{fmtUnit(s[investorKey]["1m"])}</span>
              </div>
              <span className="num text-[12px] font-medium shrink-0" style={{ color }}>{stockPct}%</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ── TOP 10 테이블 ────────────────────────────── */
function TopTable({ title, desc, stocks, type }: { title: string; desc: string; stocks: StockRanking[]; type: "buy" | "sell" }) {
  const sorted = [...stocks]
    .sort((a, b) => type === "buy" ? b.combined["1m"] - a.combined["1m"] : a.combined["1m"] - b.combined["1m"])
    .slice(0, 10);

  return (
    <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-4 sm:p-6">
      <h3 className="text-xs sm:text-sm font-medium text-[var(--text-secondary)]">{title}</h3>
      <p className="text-[10px] text-[var(--text-muted)] mb-3">{desc}</p>
      <div className="space-y-0">
        {sorted.map((s, i) => (
          <div key={s.name} className="flex items-center gap-2 py-2.5 border-t border-white/[0.03] first:border-0">
            <span className="text-[var(--text-muted)] num text-xs w-5 shrink-0 text-center">{i + 1}</span>
            <div className="flex-1 min-w-0">
              {s.ticker ? (
                <Link href={`/stocks/${s.ticker}`} className="text-white text-[13px] font-medium hover:text-[var(--accent-blue)] transition truncate block">
                  {s.name}
                </Link>
              ) : (
                <span className="text-white text-[13px] font-medium truncate block">{s.name}</span>
              )}
            </div>
            <div className="text-right shrink-0">
              <CNum v={s.combined["1m"]} />
            </div>
          </div>
        ))}
      </div>
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
    <div className="space-y-4">
      {meta && (
        <p className="text-[11px] text-[var(--text-muted)]">
          기준일 {meta.business_date} · {new Date(meta.last_updated).toLocaleString("ko-KR")} 업데이트
        </p>
      )}
      <div className="flex flex-col sm:flex-row gap-4">
        <IndexCard name="KOSPI" data={market?.KOSPI ?? null} />
        <IndexCard name="KOSDAQ" data={market?.KOSDAQ ?? null} />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <FlowChart title="KOSPI 투자자별 자금흐름" data={market?.KOSPI ?? null} />
        <FlowChart title="KOSDAQ 투자자별 자금흐름" data={market?.KOSDAQ ?? null} />
      </div>
      <ConsensusChart stocks={stocks} />
      <div className="flex flex-col sm:flex-row gap-4">
        <ConcentrationCard title="외국인 1개월 수급 집중도" stocks={stocks} investorKey="foreign" color="#f85149" />
        <ConcentrationCard title="기관 1개월 수급 집중도" stocks={stocks} investorKey="institution" color="#58a6ff" />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <TopTable title="1개월 순매수 TOP 10" desc="외국인+기관 합산 순매수 금액 기준" stocks={stocks} type="buy" />
        <TopTable title="1개월 순매도 TOP 10" desc="외국인+기관 합산 순매도 금액 기준" stocks={stocks} type="sell" />
      </div>
      <div className="text-center pt-2">
        <Link href="/stocks"
          className="inline-flex items-center gap-2 px-6 py-2.5 bg-[var(--accent-blue)] text-white rounded-xl text-sm font-medium hover:brightness-110 transition">
          전체 종목 순매수 보기
          <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor"><path d="M6.22 3.22a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06l-4.25 4.25a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042L9.94 8 6.22 4.28a.75.75 0 0 1 0-1.06Z"/></svg>
        </Link>
      </div>
    </div>
  );
}
