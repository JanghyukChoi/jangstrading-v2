"use client";

import { useEffect, useState, useMemo, Suspense } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";

export const dynamic = "force-static";

/* ── 타입 ─────────────────────────────────────── */
interface StockRanking {
  name: string;
  market: string;
  ticker?: string;
  per?: number | null;
  pbr?: number | null;
  market_cap?: number | null;
  price_change?: Record<string, number>;
  sector_mid?: string;
  foreign: Record<string, number>;
  institution: Record<string, number>;
  combined: Record<string, number>;
  pension?: Record<string, number>;
}
type Investor = "combined" | "foreign" | "institution" | "pension";
type Period = "1d" | "1w" | "1m" | "3m" | "6m";
type Signal = "all" | "buy_reversal" | "sell_reversal" | "leaders" | "accumulation" | "ai_screener";

/* ── 유틸 ─────────────────────────────────────── */
function getInvVal(s: StockRanking, inv: Investor, p: string): number {
  if (inv === "pension") return s.pension?.[p] ?? 0;
  return s[inv][p] ?? 0;
}
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
  const str = fmtUnit(v);
  const m = str.match(/^(.+?)([가-힣]+)$/);
  return m ? (
    <span className={cls}><span className="num">{m[1]}</span>{m[2]}</span>
  ) : (
    <span className={`num ${cls}`}>{str}</span>
  );
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

/* ── V3 시그널 lookup ─────────────────────────── */
// signals.json 구조: { date, signals: { buy_reversal: ticker[], sell_reversal: [], leader: [], accumulation: [] } }
interface V3Signals {
  buy_reversal: Set<string>;
  sell_reversal: Set<string>;
  leader: Set<string>;
  accumulation: Set<string>;
  ai_screener: Set<string>;
}

const SIGNAL_LABEL: Record<Exclude<Signal, "all">, { label: string; color: string }> = {
  buy_reversal: { label: "매수전환", color: "bg-emerald-500/15 text-emerald-400" },
  sell_reversal: { label: "매도전환", color: "bg-orange-500/15 text-orange-400" },
  leaders: { label: "주도주", color: "bg-amber-500/15 text-amber-400" },
  accumulation: { label: "집중매수", color: "bg-rose-500/15 text-rose-400" },
  ai_screener: { label: "AI 수급 주도주", color: "bg-indigo-500/15 text-indigo-400" },
};

function getSignals(
  s: StockRanking,
  v3: V3Signals | null
): { key: Signal; label: string; color: string }[] {
  const out: { key: Signal; label: string; color: string }[] = [];
  if (!v3 || !s.ticker) return out;
  const t = s.ticker;
  if (v3.buy_reversal.has(t)) out.push({ key: "buy_reversal", ...SIGNAL_LABEL.buy_reversal });
  if (v3.sell_reversal.has(t)) out.push({ key: "sell_reversal", ...SIGNAL_LABEL.sell_reversal });
  if (v3.leader.has(t)) out.push({ key: "leaders", ...SIGNAL_LABEL.leaders });
  if (v3.accumulation.has(t)) out.push({ key: "accumulation", ...SIGNAL_LABEL.accumulation });
  if (v3.ai_screener.has(t)) out.push({ key: "ai_screener", ...SIGNAL_LABEL.ai_screener });
  return out;
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

  // URL에서 초기값 읽기 + 로컬 상태로 관리 (router.replace freeze 방지)
  const [signalFilter, setSignalFilterState] = useState<Signal>((searchParams.get("signal") as Signal) || "all");
  const [period, setPeriodState] = useState<Period>((searchParams.get("period") as Period) || "1m");
  const [marketFilter, setMarketFilterState] = useState<"ALL" | "KOSPI" | "KOSDAQ">((searchParams.get("market") as any) || "ALL");
  const [investor, setInvestorState] = useState<Investor>((searchParams.get("investor") as Investor) || "combined");
  const [sortDir, setSortDirState] = useState<"desc" | "asc">((searchParams.get("dir") as any) || "desc");
  const [sortBy, setSortByState] = useState<"amount" | "ratio">((searchParams.get("sort") as any) || "amount");

  // URL 동기화 (freeze 없이)
  function syncUrl(updates: Record<string, string>, addHistory = false) {
    const params = new URLSearchParams(window.location.search);
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
      window.history.pushState(null, "", url);
    } else {
      window.history.replaceState(null, "", url);
    }
  }

  function setSignalFilter(v: Signal) { setSignalFilterState(v); syncUrl({ signal: v }, true); }
  function setPeriod(v: Period) { setPeriodState(v); syncUrl({ period: v }); }
  function setMarketFilter(v: "ALL" | "KOSPI" | "KOSDAQ") { setMarketFilterState(v); syncUrl({ market: v }); }
  function setInvestor(v: Investor) { setInvestorState(v); syncUrl({ investor: v }); }
  function setSortDir(v: "desc" | "asc") { setSortDirState(v); syncUrl({ dir: v }); }
  function setSortBy(v: "amount" | "ratio") { setSortByState(v); syncUrl({ sort: v }); }

  const [v3Signals, setV3Signals] = useState<V3Signals | null>(null);
  // ai_screener는 점수 desc 순서 보존 위해 ticker -> rank map도 별도 저장
  const [aiScreenerRank, setAiScreenerRank] = useState<Map<string, number>>(new Map());

  useEffect(() => {
    Promise.all([
      fetch("/data/stock-rankings.json").then((r) => r.json()),
      fetch("/data/meta.json").then((r) => r.json()),
      fetch("/data/signals.json").then((r) => r.json()).catch(() => null),
    ])
      .then(([s, m, sig]) => {
        setAllStocks(s.data);
        setMeta(m);
        if (sig?.signals) {
          const aiOrdered: string[] = sig.longterm?.ai_screener ?? [];
          setV3Signals({
            buy_reversal: new Set(sig.signals.buy_reversal ?? []),
            sell_reversal: new Set(sig.signals.sell_reversal ?? []),
            leader: new Set(sig.signals.leader ?? []),
            accumulation: new Set(sig.signals.accumulation ?? []),
            ai_screener: new Set(aiOrdered),
          });
          const rankMap = new Map<string, number>();
          aiOrdered.forEach((t, i) => rankMap.set(t, i));
          setAiScreenerRank(rankMap);
        }
      })
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
      if (signalFilter === "leaders") {
        const leaderSet = v3Signals?.leader ?? new Set<string>();
        r = r.filter((s) => s.ticker && leaderSet.has(s.ticker));
        return [...r].sort((a, b) => b.combined[period] - a.combined[period]);
      }
      if (signalFilter === "ai_screener") {
        const set = v3Signals?.ai_screener ?? new Set<string>();
        r = r.filter((s) => s.ticker && set.has(s.ticker));
        // signals.json 배열 순서 (= 점수 desc) 유지
        return [...r].sort((a, b) => {
          const ra = aiScreenerRank.get(a.ticker ?? "") ?? 999;
          const rb = aiScreenerRank.get(b.ticker ?? "") ?? 999;
          return ra - rb;
        });
      }
      r = r.filter((s) => getSignals(s, v3Signals).some((sig) => sig.key === signalFilter));
      // 신호별 최적 정렬
      return [...r].sort((a, b) => {
        switch (signalFilter) {
          case "buy_reversal": return b.combined["1w"] - a.combined["1w"];
          case "sell_reversal": return a.combined["1w"] - b.combined["1w"];
          case "accumulation": return b.combined["1m"] - a.combined["1m"];
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
        const ar = calcRatio(getInvVal(a, investor, period), a.market_cap) ?? 0;
        const br = calcRatio(getInvVal(b, investor, period), b.market_cap) ?? 0;
        return sortDir === "desc" ? br - ar : ar - br;
      }
      const av = getInvVal(a, investor, period);
      const bv = getInvVal(b, investor, period);
      return sortDir === "desc" ? bv - av : av - bv;
    });
  }, [allStocks, marketFilter, search, investor, period, sortDir, sortBy, signalFilter, v3Signals]);

  // 신호별 종목 수 카운트 (V3 결과 그대로)
  const signalCounts = useMemo(() => {
    return {
      buy_reversal: v3Signals?.buy_reversal.size ?? 0,
      sell_reversal: v3Signals?.sell_reversal.size ?? 0,
      leaders: v3Signals?.leader.size ?? 0,
      accumulation: v3Signals?.accumulation.size ?? 0,
      ai_screener: v3Signals?.ai_screener.size ?? 0,
    };
  }, [v3Signals]);

  // 신호 활성 시 표시 기간 자동 결정
  const displayPeriod: Period = signalFilter === "all" || signalFilter === "leaders" ? period :
    (signalFilter === "buy_reversal" || signalFilter === "sell_reversal") ? "1w" : "1m";

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const paged = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const maxVal = paged.length > 0 ? Math.max(...paged.map((s) => Math.abs(getInvVal(s, investor, displayPeriod))), 1) : 1;
  const hasPer = allStocks.some((s) => s.per != null);

  useEffect(() => setPage(0), [search, marketFilter, investor, period, sortDir, sortBy, signalFilter]);

  const invLabels: Record<Investor, string> = { combined: "외국인+기관", foreign: "외국인", institution: "기관", pension: "연기금" };
  const periodLabels: Record<Period, string> = { "1d": "1일", "1w": "1주", "1m": "1개월", "3m": "3개월", "6m": "6개월" };

  if (loading) {
    return (
      <div className="space-y-4">
        {/* 헤더 스켈레톤 */}
        <div className="flex items-end justify-between gap-2">
          <div className="space-y-2">
            <div className="h-6 w-48 bg-white/[0.04] rounded animate-pulse" />
            <div className="h-3 w-32 bg-white/[0.04] rounded animate-pulse" />
          </div>
          <div className="h-3 w-16 bg-white/[0.04] rounded animate-pulse" />
        </div>
        {/* 필터 칩 스켈레톤 */}
        <div className="flex gap-2 flex-wrap">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-7 w-20 bg-white/[0.04] rounded-xl animate-pulse" />
          ))}
        </div>
        {/* 컨트롤 스켈레톤 */}
        <div className="flex gap-2 flex-wrap">
          <div className="h-8 w-44 bg-white/[0.04] rounded-xl animate-pulse" />
          <div className="h-8 w-36 bg-white/[0.04] rounded-xl animate-pulse" />
          <div className="h-8 w-24 bg-white/[0.04] rounded-xl animate-pulse" />
        </div>
        {/* 테이블 스켈레톤 */}
        <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-4 space-y-3">
          {Array.from({ length: 10 }).map((_, i) => (
            <div key={i} className="flex items-center justify-between gap-3 py-1">
              <div className="flex items-center gap-3 flex-1 min-w-0">
                <div className="h-3 w-4 bg-white/[0.04] rounded animate-pulse shrink-0" />
                <div className="h-4 w-28 sm:w-40 bg-white/[0.04] rounded animate-pulse" />
              </div>
              <div className="h-4 w-16 sm:w-20 bg-white/[0.04] rounded animate-pulse shrink-0" />
              <div className="h-4 w-16 sm:w-20 bg-white/[0.04] rounded animate-pulse shrink-0 hidden sm:block" />
              <div className="h-4 w-20 bg-white/[0.04] rounded animate-pulse shrink-0" />
            </div>
          ))}
        </div>
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

      {/* Sticky 필터 영역 */}
      <div className="sticky top-14 z-30 -mx-5 px-5 py-3 bg-[#06080d]/90 backdrop-blur-xl border-b border-white/[0.06] space-y-3">
      {/* 신호 필터 카드 */}
      <div className="flex flex-wrap gap-2">
        {([
          { key: "all" as Signal, label: "전체", count: null, dot: "" },
          { key: "buy_reversal" as Signal, label: "매수전환", count: signalCounts.buy_reversal, dot: "bg-emerald-400" },
          { key: "sell_reversal" as Signal, label: "매도전환", count: signalCounts.sell_reversal, dot: "bg-orange-400" },
          { key: "leaders" as Signal, label: "주도주", count: signalCounts.leaders, dot: "bg-amber-400" },
          { key: "accumulation" as Signal, label: "집중매수", count: signalCounts.accumulation, dot: "bg-rose-400" },
          { key: "ai_screener" as Signal, label: "AI 수급 주도주", count: signalCounts.ai_screener, dot: "bg-indigo-400" },
        ]).map((s) => (
          <button
            key={s.key}
            onClick={() => setSignalFilter(s.key)}
            className={`px-3 py-1.5 rounded-xl text-[11px] sm:text-[12px] border transition inline-flex items-center gap-1.5 ${
              signalFilter === s.key
                ? "bg-white/[0.08] border-white/[0.15] text-white font-medium"
                : "bg-[var(--bg-card)] border-white/[0.06] text-[var(--text-secondary)] hover:border-white/[0.12]"
            }`}
          >
            {s.dot && <span className={`inline-block w-1.5 h-1.5 rounded-full ${s.dot}`} />}
            {s.label}
            {s.count != null && <span className="opacity-60">{s.count}</span>}
          </button>
        ))}
      </div>

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
            <select
              value={investor}
              onChange={(e) => setInvestor(e.target.value as Investor)}
              className="bg-[var(--bg-card)] border border-white/[0.06] rounded-xl px-3 py-[7px] text-[11px] sm:text-[12px] text-[var(--text-secondary)] outline-none cursor-pointer"
            >
              {Object.entries(invLabels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
        )}
        {(signalFilter === "all" || signalFilter === "leaders") && (
          <>
            <FilterGroup
              options={Object.entries(periodLabels).map(([k, v]) => ({ key: k as Period, label: v }))}
              value={period} onChange={setPeriod}
            />
            {signalFilter === "all" && (
            <>
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
          </>
        )}
      </div>
      </div>
      {/* /Sticky 필터 영역 */}

      {/* 신호 설명 (필터 선택 시) */}
      {signalFilter !== "all" && (
        <div className="text-sm text-[var(--text-secondary)] bg-white/[0.03] rounded-xl px-5 py-4 border border-white/[0.06]">
          {signalFilter === "buy_reversal" && "최근 3개월간 외국인이 꾸준히 팔던 종목 중, 지난 5일 사이 외국인과 기관이 동시에 사기 시작한 반등 후보. 주가는 60일 평균 아래, 거래량도 늘어남."}
          {signalFilter === "sell_reversal" && "최근 3개월간 외국인이 꾸준히 사들이던 종목 중, 지난 5일 사이 외국인과 기관이 동시에 팔기 시작한 위험 신호. 주가는 60일 평균 위에서 거래량 증가와 함께 매도 전환."}
          {signalFilter === "leaders" && "외국인과 기관이 60일 동안 함께 매수하며 주가도 강하게 오른 시장 주도 종목. 시가총액 1천억 이상, 거래량 급증 포함."}
          {signalFilter === "accumulation" && "외국인과 기관이 20일 내내 사들이고, 최근 5일 매수 강도가 더 빨라진 종목. 주가는 60일 평균 위에서 모멘텀 가속 중."}
          {signalFilter === "ai_screener" && "스마트 머니가 매집 중인 핵심 종목. 다중 지표를 AI로 합성해 매일 검증된 5종목을 선별."}
        </div>
      )}

      {/* 테이블 + 모바일 카드 */}
      <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl overflow-hidden">
        {/* 데스크톱 테이블 */}
        <div className="hidden md:block overflow-x-auto">
          <table className="w-full text-[12px] sm:text-[13px]">
            <thead>
              <tr className="text-[var(--text-muted)] text-[10px] sm:text-[11px] border-b border-white/[0.06]">
                <th className="text-left px-3 sm:px-5 py-3 font-normal w-8">#</th>
                <th className="text-left px-2 sm:px-3 py-3 font-normal">종목</th>
                <th className="text-left px-2 py-3 font-normal w-14 hidden sm:table-cell">시장</th>
                {hasPer && <th className="text-right px-2 py-3 font-normal hidden md:table-cell">PER</th>}
                <th className="text-right px-2 sm:px-3 py-3 font-normal">외국인{signalFilter !== "all" && ` (${periodLabels[displayPeriod]})`}</th>
                <th className="text-right px-2 sm:px-3 py-3 font-normal">기관{signalFilter !== "all" && ` (${periodLabels[displayPeriod]})`}</th>
                <th className="text-right px-2 sm:px-3 py-3 font-normal">{investor === "pension" ? "연기금" : "합계"}{signalFilter !== "all" && ` (${periodLabels[displayPeriod]})`}</th>
                <th className="text-right px-2 sm:px-3 py-3 font-normal hidden sm:table-cell">시총대비</th>
                <th className="text-right px-2 sm:px-3 py-3 font-normal">수익률</th>
              </tr>
            </thead>
            <tbody>
              {paged.map((s, i) => {
                const pc = s.price_change?.[displayPeriod];
                const ratio = calcRatio(getInvVal(s, investor, displayPeriod), s.market_cap);
                const signals = getSignals(s, v3Signals);
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
                    <td className="px-2 sm:px-3 py-2.5 text-right font-medium"><CNum v={investor === "pension" ? (s.pension?.[displayPeriod] ?? 0) : s.combined[displayPeriod]} /></td>
                    <td className="px-2 sm:px-3 py-2.5 text-right hidden sm:table-cell">
                      {ratio != null ? (
                        <span className={`num text-xs ${ratio > 0 ? "positive" : ratio < 0 ? "negative" : ""}`}>
                          {ratio > 0 ? "+" : ""}{ratio.toFixed(2)}%
                        </span>
                      ) : <span className="text-[var(--text-muted)]">-</span>}
                    </td>
                    <td className="px-2 sm:px-3 py-2.5 text-right">
                      {pc != null ? (
                        <span className={`num text-xs ${pc > 0 ? "positive" : pc < 0 ? "negative" : ""}`}>
                          {pc > 0 ? "+" : ""}{pc.toFixed(1)}%
                        </span>
                      ) : (
                        <span className="text-[var(--text-muted)]">-</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* 모바일 카드 리스트 */}
        <div className="md:hidden divide-y divide-white/[0.04]">
          {paged.map((s, i) => {
            const pc = s.price_change?.[displayPeriod];
            const ratio = calcRatio(getInvVal(s, investor, displayPeriod), s.market_cap);
            const signals = getSignals(s, v3Signals);
            const inner = (
              <div className="px-4 py-3.5">
                {/* 상단: 순위 + 종목명 + 수익률 */}
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-[var(--text-muted)] num text-[11px] w-5 shrink-0">{page * PAGE_SIZE + i + 1}</span>
                  <span className="text-white font-medium text-[14px] flex-1 truncate">{s.name}</span>
                  {pc != null && (
                    <span className={`text-[12px] font-medium ${pc > 0 ? "positive" : pc < 0 ? "negative" : ""}`}>
                      <span className="num">{pc > 0 ? "+" : ""}{pc.toFixed(1)}%</span>
                    </span>
                  )}
                </div>

                {/* 시장/PER/신호 배지들 */}
                <div className="flex items-center gap-1.5 ml-7 mb-3 flex-wrap">
                  <span className={`text-[9px] px-1.5 py-0.5 rounded font-medium ${
                    s.market === "KOSPI" ? "bg-blue-500/10 text-blue-400" : "bg-purple-500/10 text-purple-400"
                  }`}>{s.market}</span>
                  {hasPer && s.per != null && (
                    <span className="text-[10px] text-[var(--text-muted)]">PER <span className="num">{s.per.toFixed(1)}</span></span>
                  )}
                  {signals.map((sig) => (
                    <span key={sig.key} className={`text-[9px] px-1.5 py-0.5 rounded-md ${sig.color}`}>{sig.label}</span>
                  ))}
                </div>

                {/* 구분선 */}
                <div className="h-px bg-white/[0.04] mb-3 ml-7" />

                {/* 값 영역 */}
                <div className="ml-7 grid grid-cols-2 gap-y-1.5 gap-x-4 text-[12px]">
                  <div className="flex justify-between gap-2">
                    <span className="text-[var(--text-muted)] shrink-0">외국인</span>
                    <CNum v={s.foreign[displayPeriod]} />
                  </div>
                  <div className="flex justify-between gap-2">
                    <span className="text-[var(--text-muted)] shrink-0">기관</span>
                    <CNum v={s.institution[displayPeriod]} />
                  </div>
                  <div className="flex justify-between gap-2 font-medium">
                    <span className="text-[var(--text-muted)] font-normal shrink-0">합계</span>
                    <CNum v={investor === "pension" ? (s.pension?.[displayPeriod] ?? 0) : s.combined[displayPeriod]} />
                  </div>
                  {ratio != null && (
                    <div className="flex justify-between gap-2">
                      <span className="text-[var(--text-muted)] shrink-0">시총대비</span>
                      <span className={`${ratio > 0 ? "positive" : ratio < 0 ? "negative" : ""}`}>
                        <span className="num">{ratio > 0 ? "+" : ""}{ratio.toFixed(2)}%</span>
                      </span>
                    </div>
                  )}
                </div>
              </div>
            );
            return s.ticker ? (
              <Link key={s.name} href={`/stocks/${s.ticker}`} className="block hover:bg-white/[0.02] transition">{inner}</Link>
            ) : (
              <div key={s.name}>{inner}</div>
            );
          })}
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
