"use client";

import { useEffect, useState, useMemo, Suspense } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";

/* ── 타입 ─────────────────────────────────────── */
interface StockRanking {
  name: string;
  market: string;
  ticker?: string;
  per?: number | null;
  pbr?: number | null;
  market_cap?: number | null;
  price_change?: Record<string, number>;
  foreign: Record<string, number>;
  institution: Record<string, number>;
  combined: Record<string, number>;
}
type Investor = "combined" | "foreign" | "institution";
type Period = "1d" | "1w" | "1m" | "3m" | "6m";
type Signal = "all" | "buy_reversal" | "sell_reversal" | "divergence" | "accumulation";

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
function calcRatio(combined: number, marketCap: number | null | undefined): number | null {
  if (!marketCap || marketCap <= 0) return null;
  return combined / marketCap;
}
function PurchaseBar({ value, max }: { value: number; max: number }) {
  const pct = max === 0 ? 0 : Math.min(Math.abs(value) / max * 100, 100);
  const bg = value >= 0
    ? "bg-gradient-to-r from-red-500/70 to-red-500/10"
    : "bg-gradient-to-l from-blue-400/70 to-blue-400/10";
  return (
    <div className="w-16 h-[5px] rounded-full bg-white/[0.04] overflow-hidden">
      <div className={`h-full rounded-full ${bg}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

/* ── 신호 감지 ────────────────────────────────── */
function getSignals(s: StockRanking): { key: Signal; label: string; color: string }[] {
  const signals: { key: Signal; label: string; color: string }[] = [];
  const c = s.combined;
  const pc = s.price_change;

  // 매수전환: 3개월 50억+ 순매도 → 1주 5억+ 순매수 전환
  if (c["3m"] < -5000 && c["1w"] > 500) {
    signals.push({ key: "buy_reversal", label: "매수전환", color: "bg-emerald-500/15 text-emerald-400" });
  }

  // 매도전환: 3개월 50억+ 순매수 → 1주 5억+ 순매도 전환
  if (c["3m"] > 5000 && c["1w"] < -500) {
    signals.push({ key: "sell_reversal", label: "매도전환", color: "bg-orange-500/15 text-orange-400" });
  }

  // 괴리: 1개월 50억+ 순매수인데 주가 5%+ 하락
  if (pc && c["1m"] > 5000 && (pc["1m"] ?? 0) < -5) {
    signals.push({ key: "divergence", label: "괴리", color: "bg-amber-500/15 text-amber-400" });
  }

  // 집중매수: 1일/1주/1개월 전부 양수 + 1개월 50억+ + 규모 증가세
  if (c["1d"] > 50 && c["1w"] > 500 && c["1m"] > 5000 && c["1w"] > c["1d"] * 3) {
    signals.push({ key: "accumulation", label: "집중매수", color: "bg-rose-500/15 text-rose-400" });
  }

  return signals;
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
function StocksPageInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [allStocks, setAllStocks] = useState<StockRanking[]>([]);
  const [meta, setMeta] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 50;

  // URL에서 필터 상태 읽기
  const signalFilter = (searchParams.get("signal") as Signal) || "all";
  const period = (searchParams.get("period") as Period) || "1m";
  const marketFilter = (searchParams.get("market") as "ALL" | "KOSPI" | "KOSDAQ") || "ALL";
  const investor = (searchParams.get("investor") as Investor) || "combined";
  const sortDir = (searchParams.get("dir") as "desc" | "asc") || "desc";
  const sortBy = (searchParams.get("sort") as "amount" | "ratio") || "amount";

  // URL 파라미터 업데이트
  function updateParams(updates: Record<string, string>, addHistory = false) {
    const params = new URLSearchParams(searchParams.toString());
    for (const [k, v] of Object.entries(updates)) {
      if (v === "all" || v === "1m" || v === "ALL" || v === "combined" || v === "desc" || v === "amount") {
        params.delete(k);
      } else {
        params.set(k, v);
      }
    }
    const qs = params.toString();
    const url = `/stocks${qs ? `?${qs}` : ""}`;
    if (addHistory) {
      router.push(url, { scroll: false });
    } else {
      router.replace(url, { scroll: false });
    }
  }

  function setSignalFilter(v: Signal) { updateParams({ signal: v }, true); } // 탭 → 히스토리 O
  function setPeriod(v: Period) { updateParams({ period: v }); }
  function setMarketFilter(v: "ALL" | "KOSPI" | "KOSDAQ") { updateParams({ market: v }); }
  function setInvestor(v: Investor) { updateParams({ investor: v }); }
  function setSortDir(v: "desc" | "asc") { updateParams({ dir: v }); }
  function setSortBy(v: "amount" | "ratio") { updateParams({ sort: v }); }

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

    // 신호 필터 → 자동 정렬
    if (signalFilter !== "all") {
      r = r.filter((s) => getSignals(s).some((sig) => sig.key === signalFilter));
      // 신호별 최적 정렬
      return [...r].sort((a, b) => {
        switch (signalFilter) {
          case "buy_reversal": return b.combined["1w"] - a.combined["1w"]; // 1주 순매수 큰 순
          case "sell_reversal": return a.combined["1w"] - b.combined["1w"]; // 1주 순매도 큰 순
          case "divergence": return b.combined["1m"] - a.combined["1m"]; // 1개월 순매수 큰 순
          case "accumulation": return b.combined["1m"] - a.combined["1m"]; // 1개월 순매수 큰 순
          default: return 0;
        }
      });
    }

    // 시총대비 정렬 시: 시총 1000억 이상 + 스팩 제외
    if (sortBy === "ratio") {
      r = r.filter((s) => (s.market_cap ?? 0) >= 1000 && !s.name.includes("스팩") && !s.name.includes("SPAC"));
    }
    return [...r].sort((a, b) => {
      if (sortBy === "ratio") {
        const ar = calcRatio(a[investor][period], a.market_cap) ?? 0;
        const br = calcRatio(b[investor][period], b.market_cap) ?? 0;
        return sortDir === "desc" ? br - ar : ar - br;
      }
      const av = a[investor][period] ?? 0;
      const bv = b[investor][period] ?? 0;
      return sortDir === "desc" ? bv - av : av - bv;
    });
  }, [allStocks, marketFilter, search, investor, period, sortDir, sortBy, signalFilter]);

  // 신호별 종목 수 카운트
  const signalCounts = useMemo(() => {
    const stocks = allStocks.filter((s) => (s.market_cap ?? 0) >= 1000);
    return {
      buy_reversal: stocks.filter((s) => getSignals(s).some((sig) => sig.key === "buy_reversal")).length,
      sell_reversal: stocks.filter((s) => getSignals(s).some((sig) => sig.key === "sell_reversal")).length,
      divergence: stocks.filter((s) => getSignals(s).some((sig) => sig.key === "divergence")).length,
      accumulation: stocks.filter((s) => getSignals(s).some((sig) => sig.key === "accumulation")).length,
    };
  }, [allStocks]);

  // 신호 활성 시 표시 기간 자동 결정
  const displayPeriod: Period = signalFilter === "all" ? period :
    (signalFilter === "buy_reversal" || signalFilter === "sell_reversal") ? "1w" : "1m";

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const paged = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const maxVal = paged.length > 0 ? Math.max(...paged.map((s) => Math.abs(s[investor][displayPeriod])), 1) : 1;
  const hasPer = allStocks.some((s) => s.per != null);

  useEffect(() => setPage(0), [search, marketFilter, investor, period, sortDir, sortBy, signalFilter]);

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
      <div className="flex items-end justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-lg sm:text-xl font-semibold tracking-tight">종목별 순매수 랭킹</h1>
          {meta && <p className="text-[11px] text-[var(--text-muted)] mt-1">기준일 {meta.business_date}</p>}
        </div>
        <div className="text-xs text-[var(--text-muted)] num">{filtered.length}개 종목</div>
      </div>

      {/* 신호 필터 카드 */}
      <div className="flex flex-wrap gap-2">
        {([
          { key: "all" as Signal, label: "전체", count: null, color: "" },
          { key: "buy_reversal" as Signal, label: "🔄 매수전환", count: signalCounts.buy_reversal, color: "text-emerald-400" },
          { key: "sell_reversal" as Signal, label: "🔄 매도전환", count: signalCounts.sell_reversal, color: "text-orange-400" },
          { key: "divergence" as Signal, label: "⚡ 수급+주가 괴리", count: signalCounts.divergence, color: "text-amber-400" },
          { key: "accumulation" as Signal, label: "🔥 집중매수", count: signalCounts.accumulation, color: "text-rose-400" },
        ]).map((s) => (
          <button
            key={s.key}
            onClick={() => setSignalFilter(s.key)}
            className={`px-3 py-1.5 rounded-xl text-[11px] sm:text-[12px] border transition ${
              signalFilter === s.key
                ? "bg-white/[0.08] border-white/[0.15] text-white font-medium"
                : "bg-[var(--bg-card)] border-white/[0.06] text-[var(--text-secondary)] hover:border-white/[0.12]"
            }`}
          >
            {s.label}
            {s.count != null && <span className="ml-1 opacity-60">{s.count}</span>}
          </button>
        ))}
      </div>

      {/* 신호 설명 (필터 선택 시) */}
      {signalFilter !== "all" && (
        <div className="text-sm text-[var(--text-secondary)] bg-white/[0.03] rounded-xl px-5 py-4 border border-white/[0.06]">
          {signalFilter === "buy_reversal" && "3개월간 50억원 이상 순매도했으나, 최근 1주일 5억원 이상 순매수로 전환된 종목 (시총 1천억 이상)"}
          {signalFilter === "sell_reversal" && "3개월간 50억원 이상 순매수했으나, 최근 1주일 5억원 이상 순매도로 전환된 종목 (시총 1천억 이상)"}
          {signalFilter === "divergence" && "1개월간 50억원 이상 순매수인데 주가는 5% 이상 하락한 종목 — 수급과 가격의 괴리"}
          {signalFilter === "accumulation" && "1일 · 1주 · 1개월 연속 순매수 중이며, 1개월 50억원 이상 + 매수 규모가 증가하는 종목"}
        </div>
      )}

      {/* 필터 바 */}
      <div className="flex flex-wrap gap-2 items-center">
        <div className="relative">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
            <path d="M10.68 11.74a6 6 0 0 1-7.922-8.982 6 6 0 0 1 8.982 7.922l3.04 3.04a.749.749 0 0 1-.326 1.275.749.749 0 0 1-.734-.215ZM11.5 7a4.499 4.499 0 1 0-8.997 0A4.499 4.499 0 0 0 11.5 7Z"/>
          </svg>
          <input
            type="text"
            placeholder="종목 검색..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="bg-[var(--bg-card)] border border-white/[0.06] rounded-xl pl-9 pr-3 py-[7px] text-[13px] text-white placeholder:text-[var(--text-muted)] outline-none focus:border-[var(--accent-blue)] w-44 sm:w-52 transition"
          />
        </div>
        <FilterGroup
          options={[{ key: "ALL" as const, label: "전체" }, { key: "KOSPI" as const, label: "KOSPI" }, { key: "KOSDAQ" as const, label: "KOSDAQ" }]}
          value={marketFilter} onChange={setMarketFilter}
        />
        {signalFilter === "all" && (
          <>
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
              onClick={() => setSortDir(sortDir === "desc" ? "asc" : "desc")}
              className="bg-[var(--bg-card)] border border-white/[0.06] rounded-xl px-3 py-[7px] text-[11px] sm:text-[12px] text-[var(--text-secondary)] hover:text-white transition cursor-pointer"
            >
              {sortDir === "desc" ? "↓ 순매수" : "↑ 순매도"}
            </button>
            <button
              onClick={() => setSortBy(sortBy === "amount" ? "ratio" : "amount")}
              className={`border rounded-xl px-3 py-[7px] text-[11px] sm:text-[12px] transition cursor-pointer ${
                sortBy === "ratio"
                  ? "bg-[var(--accent-amber)] border-[var(--accent-amber)] text-black font-medium"
                  : "bg-[var(--bg-card)] border-white/[0.06] text-[var(--text-secondary)] hover:text-white"
              }`}
            >
              {sortBy === "ratio" ? "★ 시총대비" : "시총대비"}
            </button>
          </>
        )}
      </div>

      {/* 테이블 */}
      <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-[12px] sm:text-[13px]">
            <thead>
              <tr className="text-[var(--text-muted)] text-[10px] sm:text-[11px] border-b border-white/[0.06]">
                <th className="text-left px-3 sm:px-5 py-3 font-normal w-8">#</th>
                <th className="text-left px-2 sm:px-3 py-3 font-normal">종목</th>
                <th className="text-left px-2 py-3 font-normal w-14 hidden sm:table-cell">시장</th>
                {hasPer && <th className="text-right px-2 py-3 font-normal hidden md:table-cell">PER</th>}
                <th className="text-right px-2 sm:px-3 py-3 font-normal">외국인{signalFilter !== "all" && ` (${periodLabels[displayPeriod]})`}</th>
                <th className="text-right px-2 sm:px-3 py-3 font-normal">기관{signalFilter !== "all" && ` (${periodLabels[displayPeriod]})`}</th>
                <th className="text-right px-2 sm:px-3 py-3 font-normal">합계{signalFilter !== "all" && ` (${periodLabels[displayPeriod]})`}</th>
                <th className="text-right px-2 sm:px-3 py-3 font-normal">시총대비</th>
                <th className="px-3 py-3 w-16 hidden sm:table-cell"></th>
              </tr>
            </thead>
            <tbody>
              {paged.map((s, i) => {
                const ratio = calcRatio(s[investor][displayPeriod], s.market_cap);
                const signals = getSignals(s);
                return (
                  <tr key={s.name} className="border-t border-white/[0.03] hover:bg-white/[0.02] transition">
                    <td className="px-3 sm:px-5 py-2.5 text-[var(--text-muted)] num text-xs">{page * PAGE_SIZE + i + 1}</td>
                    <td className="px-2 sm:px-3 py-2.5">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        {s.ticker ? (
                          <Link href={`/stocks/${s.ticker}`} className="text-white font-medium hover:text-[var(--accent-blue)] transition">
                            {s.name}
                          </Link>
                        ) : (
                          <span className="text-white font-medium">{s.name}</span>
                        )}
                        {signals.map((sig) => (
                          <span key={sig.key} className={`text-[9px] px-1.5 py-0.5 rounded-md ${sig.color}`}>
                            {sig.label}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="px-2 py-2.5 hidden sm:table-cell">
                      <span className={`text-[10px] px-2 py-0.5 rounded-md font-medium ${
                        s.market === "KOSPI" ? "bg-blue-500/10 text-blue-400" : "bg-purple-500/10 text-purple-400"
                      }`}>{s.market}</span>
                    </td>
                    {hasPer && (
                      <td className="px-2 py-2.5 text-right num text-[var(--text-secondary)] hidden md:table-cell">
                        {s.per != null ? s.per.toFixed(1) : "-"}
                      </td>
                    )}
                    <td className="px-2 sm:px-3 py-2.5 text-right"><CNum v={s.foreign[displayPeriod]} /></td>
                    <td className="px-2 sm:px-3 py-2.5 text-right"><CNum v={s.institution[displayPeriod]} /></td>
                    <td className="px-2 sm:px-3 py-2.5 text-right font-medium"><CNum v={s.combined[displayPeriod]} /></td>
                    <td className="px-2 sm:px-3 py-2.5 text-right">
                      {ratio != null ? (
                        <span className={`num text-xs ${ratio > 0 ? "positive" : ratio < 0 ? "negative" : ""}`}>
                          {ratio > 0 ? "+" : ""}{ratio.toFixed(2)}%
                        </span>
                      ) : (
                        <span className="text-[var(--text-muted)]">-</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 hidden sm:table-cell"><PurchaseBar value={s[investor][displayPeriod]} max={maxVal} /></td>
                  </tr>
                );
              })}
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

export default function StocksPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center h-64"><div className="w-5 h-5 border-2 border-[var(--accent-blue)] border-t-transparent rounded-full animate-spin" /></div>}>
      <StocksPageInner />
    </Suspense>
  );
}
