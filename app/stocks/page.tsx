"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";

/* ── 타입 ─────────────────────────────────────── */
interface StockRanking {
  name: string;
  market: string;
  ticker?: string;
  per?: number | null;
  pbr?: number | null;
  foreign: Record<string, number>;
  institution: Record<string, number>;
  combined: Record<string, number>;
}
type Investor = "combined" | "foreign" | "institution";
type Period = "1d" | "1w" | "1m" | "3m" | "6m";

/* ── 유틸 ─────────────────────────────────────── */
function fmt(n: number) {
  return n.toLocaleString("ko-KR", { maximumFractionDigits: 1 });
}
function CNum({ v }: { v: number }) {
  const cls = v > 0 ? "positive" : v < 0 ? "negative" : "text-[var(--text-secondary)]";
  return <span className={`num ${cls}`}>{v > 0 ? "+" : ""}{fmt(v)}</span>;
}
function PurchaseBar({ value, max }: { value: number; max: number }) {
  const pct = max === 0 ? 0 : Math.min(Math.abs(value) / max * 100, 100);
  const bg = value >= 0
    ? "bg-gradient-to-r from-red-500/70 to-red-500/10"
    : "bg-gradient-to-l from-blue-400/70 to-blue-400/10";
  return (
    <div className="w-20 h-[5px] rounded-full bg-white/[0.04] overflow-hidden">
      <div className={`h-full rounded-full ${bg}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

/* ── 필터 버튼 ────────────────────────────────── */
function FilterGroup<T extends string>({
  options, value, onChange,
}: { options: { key: T; label: string }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="flex rounded-xl overflow-hidden border border-white/[0.06] bg-[var(--bg-card)]">
      {options.map((o) => (
        <button
          key={o.key}
          onClick={() => onChange(o.key)}
          className={`px-3.5 py-[7px] text-[12px] transition-all ${
            value === o.key
              ? "bg-[var(--accent-blue)] text-white font-medium"
              : "text-[var(--text-secondary)] hover:text-white hover:bg-white/[0.04]"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/* ── 메인 ─────────────────────────────────────── */
export default function StocksPage() {
  const [allStocks, setAllStocks] = useState<StockRanking[]>([]);
  const [meta, setMeta] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [marketFilter, setMarketFilter] = useState<"ALL" | "KOSPI" | "KOSDAQ">("ALL");
  const [investor, setInvestor] = useState<Investor>("combined");
  const [period, setPeriod] = useState<Period>("1m");
  const [sortDir, setSortDir] = useState<"desc" | "asc">("desc");
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 50;

  useEffect(() => {
    Promise.all([
      fetch("/data/stock-rankings.json").then((r) => r.json()),
      fetch("/data/meta.json").then((r) => r.json()),
    ])
      .then(([s, m]) => { setAllStocks(s.data); setMeta(m); })
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    let r = allStocks;
    if (marketFilter !== "ALL") r = r.filter((s) => s.market === marketFilter);
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      r = r.filter((s) => s.name.toLowerCase().includes(q));
    }
    return [...r].sort((a, b) => {
      const av = a[investor][period] ?? 0;
      const bv = b[investor][period] ?? 0;
      return sortDir === "desc" ? bv - av : av - bv;
    });
  }, [allStocks, marketFilter, search, investor, period, sortDir]);

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const paged = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const maxVal = paged.length > 0 ? Math.max(...paged.map((s) => Math.abs(s[investor][period])), 1) : 1;
  const hasPer = allStocks.some((s) => s.per != null);

  useEffect(() => setPage(0), [search, marketFilter, investor, period, sortDir]);

  const invLabels: Record<Investor, string> = { combined: "외국인+기관", foreign: "외국인", institution: "기관" };
  const periodLabels: Record<Period, string> = { "1d": "1일", "1w": "1주", "1m": "1개월", "3m": "3개월", "6m": "6개월" };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-5 h-5 border-2 border-[var(--accent-blue)] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">종목별 순매수 랭킹</h1>
          {meta && <p className="text-[11px] text-[var(--text-muted)] mt-1">기준일 {meta.business_date} · 단위: 백만원</p>}
        </div>
        <div className="text-xs text-[var(--text-muted)] num">{filtered.length}개 종목</div>
      </div>

      {/* 필터 바 */}
      <div className="flex flex-wrap gap-2.5 items-center">
        <div className="relative">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
            <path d="M10.68 11.74a6 6 0 0 1-7.922-8.982 6 6 0 0 1 8.982 7.922l3.04 3.04a.749.749 0 0 1-.326 1.275.749.749 0 0 1-.734-.215ZM11.5 7a4.499 4.499 0 1 0-8.997 0A4.499 4.499 0 0 0 11.5 7Z"/>
          </svg>
          <input
            type="text"
            placeholder="종목 검색..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="bg-[var(--bg-card)] border border-white/[0.06] rounded-xl pl-9 pr-3 py-[7px] text-[13px] text-white placeholder:text-[var(--text-muted)] outline-none focus:border-[var(--accent-blue)] w-52 transition"
          />
        </div>
        <FilterGroup
          options={[{ key: "ALL" as const, label: "전체" }, { key: "KOSPI" as const, label: "KOSPI" }, { key: "KOSDAQ" as const, label: "KOSDAQ" }]}
          value={marketFilter} onChange={setMarketFilter}
        />
        <select
          value={investor}
          onChange={(e) => setInvestor(e.target.value as Investor)}
          className="bg-[var(--bg-card)] border border-white/[0.06] rounded-xl px-3 py-[7px] text-[12px] text-[var(--text-secondary)] outline-none cursor-pointer"
        >
          {Object.entries(invLabels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <FilterGroup
          options={Object.entries(periodLabels).map(([k, v]) => ({ key: k as Period, label: v }))}
          value={period} onChange={setPeriod}
        />
        <button
          onClick={() => setSortDir((d) => (d === "desc" ? "asc" : "desc"))}
          className="flex items-center gap-1 bg-[var(--bg-card)] border border-white/[0.06] rounded-xl px-3 py-[7px] text-[12px] text-[var(--text-secondary)] hover:text-white transition cursor-pointer"
        >
          {sortDir === "desc" ? "↓ 순매수" : "↑ 순매도"}
        </button>
      </div>

      {/* 테이블 */}
      <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="text-[var(--text-muted)] text-[11px] border-b border-white/[0.06]">
                <th className="text-left px-5 py-3 font-normal w-10">#</th>
                <th className="text-left px-3 py-3 font-normal">종목</th>
                <th className="text-left px-3 py-3 font-normal w-16">시장</th>
                {hasPer && <th className="text-right px-3 py-3 font-normal">PER</th>}
                <th className="text-right px-3 py-3 font-normal">외국인<span className="text-[9px] ml-0.5 opacity-50">백만</span></th>
                <th className="text-right px-3 py-3 font-normal">기관<span className="text-[9px] ml-0.5 opacity-50">백만</span></th>
                <th className="text-right px-3 py-3 font-normal">합계<span className="text-[9px] ml-0.5 opacity-50">백만</span></th>
                <th className="px-5 py-3 w-24"></th>
              </tr>
            </thead>
            <tbody>
              {paged.map((s, i) => (
                <tr key={s.name} className="border-t border-white/[0.03] hover:bg-white/[0.02] transition">
                  <td className="px-5 py-2.5 text-[var(--text-muted)] num text-xs">{page * PAGE_SIZE + i + 1}</td>
                  <td className="px-3 py-2.5">
                    {s.ticker ? (
                      <Link
                        href={`/stocks/${s.ticker}`}
                        className="text-white font-medium hover:text-[var(--accent-blue)] transition"
                      >
                        {s.name}
                      </Link>
                    ) : (
                      <span className="text-white font-medium">{s.name}</span>
                    )}
                  </td>
                  <td className="px-3 py-2.5">
                    <span className={`text-[10px] px-2 py-0.5 rounded-md font-medium ${
                      s.market === "KOSPI" ? "bg-blue-500/10 text-blue-400" : "bg-purple-500/10 text-purple-400"
                    }`}>{s.market}</span>
                  </td>
                  {hasPer && (
                    <td className="px-3 py-2.5 text-right num text-[var(--text-secondary)]">
                      {s.per != null ? s.per.toFixed(1) : <span className="text-[var(--text-muted)]">-</span>}
                    </td>
                  )}
                  <td className="px-3 py-2.5 text-right"><CNum v={s.foreign[period]} /></td>
                  <td className="px-3 py-2.5 text-right"><CNum v={s.institution[period]} /></td>
                  <td className="px-3 py-2.5 text-right font-medium"><CNum v={s.combined[period]} /></td>
                  <td className="px-5 py-2.5"><PurchaseBar value={s[investor][period]} max={maxVal} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-3 py-4 border-t border-white/[0.06]">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="px-4 py-1.5 rounded-lg text-xs bg-white/[0.04] text-[var(--text-secondary)] hover:text-white disabled:opacity-25 transition"
            >
              ← 이전
            </button>
            <span className="text-xs text-[var(--text-muted)] num">{page + 1} / {totalPages}</span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="px-4 py-1.5 rounded-lg text-xs bg-white/[0.04] text-[var(--text-secondary)] hover:text-white disabled:opacity-25 transition"
            >
              다음 →
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
