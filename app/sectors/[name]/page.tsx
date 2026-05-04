"use client";

import { useEffect, useState, useMemo, use } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

/* ── 타입 ─────────────────────────────────────── */
interface StockRanking {
  name: string;
  market: string;
  ticker?: string;
  sector?: string;
  sector_mid?: string;
  market_cap?: number | null;
  per?: number | null;
  foreign: Record<string, number>;
  institution: Record<string, number>;
  combined: Record<string, number>;
}
type Investor = "combined" | "foreign" | "institution";
type Period = "1d" | "1w" | "1m" | "3m" | "6m";

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

/* ── 메인 ─────────────────────────────────────── */
export default function SectorDetailPage({ params }: { params: Promise<{ name: string }> }) {
  const { name } = use(params);
  const sectorName = decodeURIComponent(name);
  const router = useRouter();

  const [allStocks, setAllStocks] = useState<StockRanking[]>([]);
  const [themeMap, setThemeMap] = useState<Record<string, string[]>>({});
  const [loading, setLoading] = useState(true);
  const [investor, setInvestor] = useState<Investor>("combined");
  const [period, setPeriod] = useState<Period>("1m");

  const periodLabels: Record<Period, string> = { "1d": "1일", "1w": "1주", "1m": "1개월", "3m": "3개월", "6m": "6개월" };
  const invLabels: Record<Investor, string> = { combined: "외국인+기관", foreign: "외국인", institution: "기관" };

  useEffect(() => {
    Promise.all([
      fetch("/data/stock-rankings.json").then((r) => r.json()),
      fetch("/data/theme-map.json").then((r) => r.json()).catch(() => ({})),
    ])
      .then(([s, t]) => { setAllStocks(s.data); setThemeMap(t); })
      .finally(() => setLoading(false));
  }, []);

  const sectorStocks = useMemo(() => {
    // 테마 매핑에 있으면 테마 기준, 아니면 섹터 기준
    const themeTickers = themeMap[sectorName];
    let filtered: StockRanking[];
    if (themeTickers) {
      const tickerSet = new Set(themeTickers);
      filtered = allStocks.filter((s) => s.ticker && tickerSet.has(s.ticker));
    } else {
      filtered = allStocks.filter((s) =>
        (s.sector_mid || s.sector || "기타") === sectorName ||
        (s.sector || "기타") === sectorName
      );
    }
    return filtered.sort((a, b) => {
      const av = a[investor][period] ?? 0;
      const bv = b[investor][period] ?? 0;
      return bv - av;
    });
  }, [allStocks, themeMap, sectorName, investor, period]);

  // 섹터 합계
  const totals = useMemo(() => {
    return {
      foreign: sectorStocks.reduce((sum, s) => sum + (s.foreign[period] ?? 0), 0),
      institution: sectorStocks.reduce((sum, s) => sum + (s.institution[period] ?? 0), 0),
      combined: sectorStocks.reduce((sum, s) => sum + (s.combined[period] ?? 0), 0),
    };
  }, [sectorStocks, period]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-5 h-5 border-2 border-[var(--accent-blue)] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* 헤더 */}
      <div className="flex items-center gap-3 flex-wrap">
        <button onClick={() => router.back()} className="text-[var(--text-muted)] hover:text-white transition text-sm">
          ← 섹터 목록
        </button>
        <div className="w-px h-4 bg-white/10" />
        <h1 className="text-xl sm:text-2xl font-bold">{sectorName}</h1>
        <span className="text-[var(--text-muted)] text-sm num">{sectorStocks.length}종목</span>
      </div>

      {/* 섹터 합계 */}
      <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-4 sm:p-6">
        <div className="text-[11px] text-[var(--text-muted)] mb-3">{sectorName} 업종 전체 {periodLabels[period]} 순매수</div>
        <div className="grid grid-cols-3 gap-4">
          <div className="text-center">
            <div className="text-[10px] text-[var(--text-muted)] mb-1">외국인</div>
            <div className="text-sm sm:text-base font-semibold"><CNum v={totals.foreign} /></div>
          </div>
          <div className="text-center">
            <div className="text-[10px] text-[var(--text-muted)] mb-1">기관</div>
            <div className="text-sm sm:text-base font-semibold"><CNum v={totals.institution} /></div>
          </div>
          <div className="text-center">
            <div className="text-[10px] text-[var(--text-muted)] mb-1">합계</div>
            <div className="text-sm sm:text-base font-semibold"><CNum v={totals.combined} /></div>
          </div>
        </div>
      </div>

      {/* 필터 */}
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
      </div>

      {/* 종목 리스트 */}
      <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl overflow-hidden">
        <div className="flex items-center text-[var(--text-muted)] text-[10px] sm:text-[11px] border-b border-white/[0.06] px-3 sm:px-5 py-3">
          <span className="w-8 shrink-0 hidden sm:block">#</span>
          <span className="flex-1 min-w-0">종목</span>
          <span className="w-14 text-left hidden sm:block">시장</span>
          <span className="w-16 sm:w-24 text-right shrink-0">외국인</span>
          <span className="w-16 sm:w-24 text-right shrink-0">기관</span>
          <span className="w-16 sm:w-24 text-right shrink-0">합계</span>
          <span className="w-16 text-right shrink-0 hidden sm:block">시총대비</span>
        </div>

        {sectorStocks.map((s, i) => {
          const netVal = investor === "foreign" ? s.foreign[period] : investor === "institution" ? s.institution[period] : s.combined[period];
          const ratio = s.market_cap && s.market_cap > 0 ? Math.round(netVal / s.market_cap * 1000) / 10 : null;
          return (
          <div key={s.name} className="flex items-center px-3 sm:px-5 py-2.5 border-t border-white/[0.03] hover:bg-white/[0.02] transition">
            <span className="w-8 shrink-0 text-[var(--text-muted)] num text-xs hidden sm:block">{i + 1}</span>
            <div className="flex-1 min-w-0">
              {s.ticker ? (
                <Link href={`/stocks/${s.ticker}`} className="text-white text-[11px] sm:text-[13px] font-medium hover:text-[var(--accent-blue)] transition truncate block">
                  {s.name}
                </Link>
              ) : (
                <span className="text-white text-[11px] sm:text-[13px] font-medium truncate block">{s.name}</span>
              )}
            </div>
            <span className="w-14 hidden sm:block">
              <span className={`text-[10px] px-2 py-0.5 rounded-md font-medium ${
                s.market === "KOSPI" ? "bg-blue-500/10 text-blue-400" : "bg-purple-500/10 text-purple-400"
              }`}>{s.market}</span>
            </span>
            <span className="w-16 sm:w-24 text-right shrink-0 text-[11px] sm:text-[13px]"><CNum v={s.foreign[period]} /></span>
            <span className="w-16 sm:w-24 text-right shrink-0 text-[11px] sm:text-[13px]"><CNum v={s.institution[period]} /></span>
            <span className="w-16 sm:w-24 text-right shrink-0 text-[11px] sm:text-[13px] font-medium"><CNum v={s.combined[period]} /></span>
            <span className="w-16 text-right shrink-0 hidden sm:block">
              {ratio != null ? (
                <span className={`num text-xs ${ratio > 0 ? "positive" : ratio < 0 ? "negative" : ""}`}>
                  {ratio > 0 ? "+" : ""}{ratio.toFixed(1)}%
                </span>
              ) : (
                <span className="text-[var(--text-muted)]">-</span>
              )}
            </span>
          </div>
          );
        })}
      </div>
    </div>
  );
}
