"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";

/* ── 타입 ─────────────────────────────────────── */
interface StockRanking {
  name: string;
  market: string;
  ticker?: string;
  sector?: string;
  sector_mid?: string;
  market_cap?: number | null;
  foreign: Record<string, number>;
  institution: Record<string, number>;
  combined: Record<string, number>;
}
interface SectorData {
  name: string;
  stockCount: number;
  foreign: number;
  institution: number;
  combined: number;
  totalMarketCap: number;
  ratio: number | null;
}
type Investor = "combined" | "foreign" | "institution";
type Period = "1d" | "1w" | "1m" | "3m" | "6m";
type View = "large" | "mid" | "theme";

/* ── 유틸 ─────────────────────────────────────── */
function fmtUnit(n: number) {
  const won = n * 1_000_000;
  const abs = Math.abs(won);
  const sign = won > 0 ? "+" : "";
  if (abs >= 1_000_000_000_000) return `${sign}${(won / 1_000_000_000_000).toFixed(1)}조원`;
  if (abs >= 100_000_000) return `${sign}${Math.round(won / 100_000_000).toLocaleString()}억원`;
  if (abs >= 10_000) return `${sign}${Math.round(won / 10_000).toLocaleString()}만원`;
  return `${sign}${Math.round(won).toLocaleString()}원`;
}
function CNum({ v }: { v: number }) {
  const cls = v > 0 ? "positive" : v < 0 ? "negative" : "text-[var(--text-secondary)]";
  return <span className={`num ${cls}`}>{fmtUnit(v)}</span>;
}
function fmtCap(n: number) {
  if (n >= 10000) return `${(n / 10000).toFixed(0)}조`;
  return `${Math.round(n).toLocaleString()}억`;
}
function FilterGroup<T extends string>({
  options, value, onChange,
}: { options: { key: T; label: string }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="flex rounded-xl overflow-hidden border border-white/[0.06] bg-[var(--bg-card)]">
      {options.map((o) => (
        <button
          key={o.key}
          onClick={() => onChange(o.key)}
          className={`px-3 py-[7px] text-[11px] sm:text-[12px] transition-all ${
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
function SectorBar({ value, max }: { value: number; max: number }) {
  const pct = max === 0 ? 0 : Math.min(Math.abs(value) / max * 100, 100);
  const bg = value >= 0
    ? "bg-gradient-to-r from-red-500/70 to-red-500/10"
    : "bg-gradient-to-l from-blue-400/70 to-blue-400/10";
  return (
    <div className="w-20 h-1.5 rounded-full bg-white/[0.04] overflow-hidden">
      <div className={`h-full rounded-full ${bg}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

/* ── 메인 ─────────────────────────────────────── */
export default function SectorsPage() {
  const [allStocks, setAllStocks] = useState<StockRanking[]>([]);
  const [themeMap, setThemeMap] = useState<Record<string, string[]>>({});
  const [meta, setMeta] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<View>("large");
  const [investor, setInvestor] = useState<Investor>("combined");
  const [period, setPeriod] = useState<Period>("1m");
  const [sortBy, setSortBy] = useState<"amount" | "ratio">("amount");

  const periodLabels: Record<Period, string> = { "1d": "1일", "1w": "1주", "1m": "1개월", "3m": "3개월", "6m": "6개월" };
  const invLabels: Record<Investor, string> = { combined: "외국인+기관", foreign: "외국인", institution: "기관" };

  useEffect(() => {
    Promise.all([
      fetch("/data/stock-rankings.json").then((r) => r.json()),
      fetch("/data/meta.json").then((r) => r.json()),
      fetch("/data/theme-map.json").then((r) => r.json()).catch(() => ({})),
    ])
      .then(([s, m, t]) => { setAllStocks(s.data); setMeta(m); setThemeMap(t); })
      .finally(() => setLoading(false));
  }, []);

  // 섹터별 집계
  const sectors = useMemo(() => {
    const map: Record<string, { foreign: number; institution: number; combined: number; totalCap: number; count: number }> = {};

    if (view === "theme") {
      // 테마별: theme-map.json의 ticker 리스트로 집계
      const tickerIndex: Record<string, StockRanking> = {};
      for (const s of allStocks) {
        if (s.ticker) tickerIndex[s.ticker] = s;
      }
      for (const [themeName, tickers] of Object.entries(themeMap)) {
        if (!map[themeName]) map[themeName] = { foreign: 0, institution: 0, combined: 0, totalCap: 0, count: 0 };
        for (const ticker of tickers) {
          const s = tickerIndex[ticker];
          if (!s) continue;
          map[themeName].foreign += s.foreign[period] ?? 0;
          map[themeName].institution += s.institution[period] ?? 0;
          map[themeName].combined += s.combined[period] ?? 0;
          map[themeName].totalCap += s.market_cap ?? 0;
          map[themeName].count++;
        }
      }
    } else {
      // 대분류/중분류: stock-rankings.json의 sector/sector_mid로 집계
      const groupKey = view === "large" ? "sector" : "sector_mid";
      for (const s of allStocks) {
        const key = (s as any)[groupKey] || s.sector || "기타";
        if (key === "기타") continue;
        if (!map[key]) map[key] = { foreign: 0, institution: 0, combined: 0, totalCap: 0, count: 0 };
        map[key].foreign += s.foreign[period] ?? 0;
        map[key].institution += s.institution[period] ?? 0;
        map[key].combined += s.combined[period] ?? 0;
        map[key].totalCap += s.market_cap ?? 0;
        map[key].count++;
      }
    }

    const result: SectorData[] = Object.entries(map)
      .filter(([, data]) => data.count > 0)
      .map(([name, data]) => {
        const net = investor === "foreign" ? data.foreign : investor === "institution" ? data.institution : data.combined;
        return {
          name,
          stockCount: data.count,
          foreign: Math.round(data.foreign * 10) / 10,
          institution: Math.round(data.institution * 10) / 10,
          combined: Math.round(data.combined * 10) / 10,
          totalMarketCap: Math.round(data.totalCap),
          ratio: data.totalCap > 0 ? Math.round(net / data.totalCap * 1000) / 10 : null,
        };
      });

    result.sort((a, b) => {
      if (sortBy === "ratio") return (b.ratio ?? 0) - (a.ratio ?? 0);
      const av = investor === "foreign" ? a.foreign : investor === "institution" ? a.institution : a.combined;
      const bv = investor === "foreign" ? b.foreign : investor === "institution" ? b.institution : b.combined;
      return bv - av;
    });
    return result;
  }, [allStocks, themeMap, investor, period, sortBy, view]);

  const maxVal = sectors.length > 0 ? Math.max(...sectors.map((s) => Math.abs(
    investor === "foreign" ? s.foreign : investor === "institution" ? s.institution : s.combined
  )), 1) : 1;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-5 h-5 border-2 border-[var(--accent-blue)] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-end justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-lg sm:text-xl font-semibold tracking-tight">섹터별 수급 현황</h1>
          {meta && <p className="text-[11px] text-[var(--text-muted)] mt-1">기준일 {meta.business_date} · WICS 산업분류</p>}
        </div>
        <div className="text-xs text-[var(--text-muted)] num">{sectors.length}개 업종</div>
      </div>

      {/* 대분류 / 중분류 / 테마 탭 */}
      <div className="flex items-center gap-3">
        <div className="flex rounded-xl overflow-hidden border border-white/[0.08] bg-[var(--bg-card)]">
          <button
            onClick={() => setView("large")}
            className={`px-4 py-2 text-[13px] font-medium transition ${
              view === "large" ? "bg-white/[0.1] text-white" : "text-[var(--text-secondary)] hover:text-white"
            }`}
          >
            대분류
          </button>
          <button
            onClick={() => setView("mid")}
            className={`px-4 py-2 text-[13px] font-medium transition ${
              view === "mid" ? "bg-white/[0.1] text-white" : "text-[var(--text-secondary)] hover:text-white"
            }`}
          >
            중분류
          </button>
          <button
            onClick={() => setView("theme")}
            className={`px-4 py-2 text-[13px] font-medium transition ${
              view === "theme" ? "bg-white/[0.1] text-white" : "text-[var(--text-secondary)] hover:text-white"
            }`}
          >
            테마
          </button>
        </div>
        <span className="text-[11px] text-[var(--text-muted)]">
          {view === "large" ? "10개 산업 섹터" : view === "mid" ? "25개 세부 업종" : `${sectors.length}개 테마`}
        </span>
      </div>

      {/* 필터 바 */}
      <div className="flex flex-wrap gap-2 items-center">
        <select
          value={investor}
          onChange={(e) => setInvestor(e.target.value as Investor)}
          className="bg-[var(--bg-card)] border border-white/[0.06] rounded-xl px-3 py-[7px] text-[11px] sm:text-[12px] text-[var(--text-secondary)] outline-none cursor-pointer"
        >
          {Object.entries(invLabels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <FilterGroup
          options={Object.entries(periodLabels).map(([k, v]) => ({ key: k as Period, label: v }))}
          value={period} onChange={setPeriod}
        />
        <button
          onClick={() => setSortBy((s) => (s === "amount" ? "ratio" : "amount"))}
          className={`border rounded-xl px-3 py-[7px] text-[11px] sm:text-[12px] transition cursor-pointer ${
            sortBy === "ratio"
              ? "bg-[var(--accent-amber)] border-[var(--accent-amber)] text-black font-medium"
              : "bg-[var(--bg-card)] border-white/[0.06] text-[var(--text-secondary)] hover:text-white"
          }`}
        >
          {sortBy === "ratio" ? "★ 시총대비" : "시총대비"}
        </button>
      </div>

      {/* 테이블 */}
      <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl overflow-hidden">
        <div className="flex items-center text-[var(--text-muted)] text-[10px] sm:text-[11px] border-b border-white/[0.06] px-4 sm:px-5 py-3">
          <span className="w-8 shrink-0">#</span>
          <span className="flex-1 min-w-0">업종</span>
          <span className="w-12 text-right hidden sm:block">종목수</span>
          <span className="w-16 text-right hidden sm:block">시총</span>
          <span className="w-20 sm:w-24 text-right shrink-0">외국인</span>
          <span className="w-20 sm:w-24 text-right shrink-0">기관</span>
          <span className="w-20 sm:w-24 text-right shrink-0">합계</span>
          <span className="w-14 text-right shrink-0">시총대비</span>
          <span className="w-20 hidden sm:block"></span>
        </div>

        {sectors.map((s, i) => {
          const sortVal = investor === "foreign" ? s.foreign : investor === "institution" ? s.institution : s.combined;
          return (
            <Link
              key={s.name}
              href={`/sectors/${encodeURIComponent(s.name)}`}
              className="flex items-center px-4 sm:px-5 py-3 border-t border-white/[0.03] hover:bg-white/[0.02] transition"
            >
              <span className="w-8 shrink-0 text-[var(--text-muted)] num text-xs">{i + 1}</span>
              <span className="flex-1 min-w-0 flex items-center gap-1.5">
                <span className="text-white font-medium text-[12px] sm:text-[13px] truncate">{s.name}</span>
                <svg width="10" height="10" viewBox="0 0 16 16" fill="currentColor" className="text-[var(--text-muted)] shrink-0">
                  <path d="M6.22 3.22a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06l-4.25 4.25a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042L9.94 8 6.22 4.28a.75.75 0 0 1 0-1.06Z"/>
                </svg>
              </span>
              <span className="w-12 text-right text-[var(--text-muted)] num text-[10px] hidden sm:block">{s.stockCount}</span>
              <span className="w-16 text-right text-[var(--text-muted)] num text-[10px] hidden sm:block">{fmtCap(s.totalMarketCap)}</span>
              <span className="w-20 sm:w-24 text-right shrink-0 text-[12px] sm:text-[13px]"><CNum v={s.foreign} /></span>
              <span className="w-20 sm:w-24 text-right shrink-0 text-[12px] sm:text-[13px]"><CNum v={s.institution} /></span>
              <span className="w-20 sm:w-24 text-right shrink-0 text-[12px] sm:text-[13px] font-medium"><CNum v={s.combined} /></span>
              <span className="w-14 text-right shrink-0">
                {s.ratio != null ? (
                  <span className={`num text-xs ${s.ratio > 0 ? "positive" : s.ratio < 0 ? "negative" : ""}`}>
                    {s.ratio > 0 ? "+" : ""}{s.ratio.toFixed(1)}%
                  </span>
                ) : "-"}
              </span>
              <span className="w-20 pl-3 hidden sm:block"><SectorBar value={sortVal} max={maxVal} /></span>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
