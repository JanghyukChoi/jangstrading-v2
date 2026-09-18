"use client";

import { useEffect, useState, useMemo, Suspense } from "react";
import { perLabel } from "@/app/format";
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
  /** 기타법인 — 자사주 매입·계열사 지분·M&A. 수집 시작일 이전 종목엔 없다. */
  corp?: Record<string, number>;
}
type Investor = "combined" | "foreign" | "institution" | "pension" | "corp";
type Period = "1d" | "1w" | "1m" | "3m" | "6m";

/* ── 유틸 ─────────────────────────────────────── */
function getInvVal(s: StockRanking, inv: Investor, p: string): number {
  if (inv === "pension") return s.pension?.[p] ?? 0;
  if (inv === "corp") return s.corp?.[p] ?? 0;
  return s[inv][p] ?? 0;
}

/** 합계 열에 무엇을 넣을지. 연기금·기타법인을 고르면 그 주체 값으로 바꾼다. */
function subjectVal(s: StockRanking, inv: Investor, p: Period): number {
  if (inv === "pension" || inv === "corp") return getInvVal(s, inv, p);
  return s.combined[p] ?? 0;
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
/* 시그널 5종(매수전환·매도전환·주도주·단기수급상위·장기수급상위)을 전부 내렸다.

   10.3년(2016-02~2026-05, 2,520영업일, 3,234종목, 상장폐지 포함) 재검정에서
   같은 날 같은 시총 하한 모집단 평균 대비 초과수익이 없었다. 단기 4종은
   기간을 나누면 부호가 뒤집혔고(v1 은 train, v3 는 test 에서만 작동),
   장기수급상위는 날짜군집 + Newey-West 로 t 를 제대로 재면 train 구간
   7년에서 t<1 이었다(5일 0.16 / 20일 0.65 / 60일 0.59).

   근거는 scripts/backtest_signals.py 와 scripts/backtest_longterm_check.py.
   시그널 함수는 지우지 않았으므로 재검정 후 되살릴 수 있다. */

/* ── 필터 버튼 ────────────────────────────────── */
function FilterGroup<T extends string>({
  options, value, onChange,
}: { options: { key: T; label: string }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="flex shrink-0 rounded-xl overflow-hidden border border-white/[0.06] bg-[var(--bg-card)]">
      {options.map((o) => (
        <button
          key={o.key}
          onClick={() => onChange(o.key)}
          className={`shrink-0 whitespace-nowrap px-2.5 sm:px-3 py-[5px] sm:py-[7px] text-[12px] sm:text-[13px] transition-all ${
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
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 50;

  // URL에서 초기값 읽기 + 로컬 상태로 관리 (router.replace freeze 방지)
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

  function setPeriod(v: Period) { setPeriodState(v); syncUrl({ period: v }); }
  function setMarketFilter(v: "ALL" | "KOSPI" | "KOSDAQ") { setMarketFilterState(v); syncUrl({ market: v }); }
  function setInvestor(v: Investor) { setInvestorState(v); syncUrl({ investor: v }); }
  function setSortDir(v: "desc" | "asc") { setSortDirState(v); syncUrl({ dir: v }); }
  function setSortBy(v: "amount" | "ratio") { setSortByState(v); syncUrl({ sort: v }); }

  useEffect(() => {
    Promise.all([
      fetch("/data/stock-rankings.json").then((r) => r.json()),
      fetch("/data/meta.json").then((r) => r.json()),
    ])
      .then(([s, m]) => {
        setAllStocks(s.data);
        setMeta(m);
      })
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    let r = allStocks;
    if (marketFilter !== "ALL") r = r.filter((s) => s.market === marketFilter);

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
  }, [allStocks, marketFilter, investor, period, sortDir, sortBy]);

  const displayPeriod: Period = period;

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const paged = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const maxVal = paged.length > 0 ? Math.max(...paged.map((s) => Math.abs(getInvVal(s, investor, displayPeriod))), 1) : 1;
  const hasPer = allStocks.some((s) => s.per != null);
  // 기타법인은 2026-09-18 부터 수집한다. 첫 수집 전에는 값이 전부 없어서
  // 선택지 자체를 숨긴다 — 0 만 늘어선 표를 보여주는 것보다 낫다.
  const hasCorp = allStocks.some((s) => s.corp && Object.keys(s.corp).length > 0);

  useEffect(() => setPage(0), [marketFilter, investor, period, sortDir, sortBy]);

  const invLabels: Record<Investor, string> = { combined: "외국인+기관", foreign: "외국인", institution: "기관", pension: "연기금", corp: "기타법인" };
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
        <div className="bg-[var(--bg-card)] rounded-2xl p-4 space-y-3">
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
          {meta && <p className="text-[13px] text-[var(--text-muted)] mt-1">기준일 {meta.business_date}</p>}
        </div>
        <div className="text-xs text-[var(--text-muted)] num">{filtered.length}개 종목</div>
      </div>

      {/* 필터 영역 (sticky 제거 — 스크롤 시 자연스럽게 위로) */}
      <div className="space-y-3">
      {/* 필터 바 (투자자/기간/정렬) — 모바일 가로 스크롤, 데스크톱 wrap */}
      <div className="flex sm:flex-wrap gap-1.5 sm:gap-2 items-center overflow-x-auto sm:overflow-x-visible no-scrollbar">
        <select
          value={investor}
          onChange={(e) => setInvestor(e.target.value as Investor)}
          className="shrink-0 bg-[var(--bg-card)] rounded-lg px-2.5 py-[5px] text-[12px] sm:text-[13px] text-[var(--text-secondary)] outline-none cursor-pointer"
        >
          {Object.entries(invLabels)
            .filter(([k]) => k !== "corp" || hasCorp)
            .map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <FilterGroup
          options={Object.entries(periodLabels).map(([k, v]) => ({ key: k as Period, label: v }))}
          value={period} onChange={setPeriod}
        />
        <button
          onClick={() => setSortDir(sortDir === "desc" ? "asc" : "desc")}
          className="shrink-0 whitespace-nowrap bg-[var(--bg-card)] rounded-lg px-2.5 py-[5px] text-[12px] sm:text-[13px] text-[var(--text-secondary)] hover:text-white transition cursor-pointer"
        >
          {sortDir === "desc" ? "↓ 순매수" : "↑ 순매도"}
        </button>
        <button
          onClick={() => setSortBy(sortBy === "amount" ? "ratio" : "amount")}
          className={`shrink-0 whitespace-nowrap border rounded-lg px-2.5 py-[5px] text-[12px] sm:text-[13px] transition cursor-pointer ${
            sortBy === "ratio"
              ? "bg-[var(--accent-amber)] border-[var(--accent-amber)] text-black font-medium"
              : "bg-[var(--bg-card)] border-white/[0.06] text-[var(--text-secondary)] hover:text-white"
          }`}
        >
          {sortBy === "ratio" ? "★ 시총대비" : "시총대비"}
        </button>
      </div>

      {/* 시장 필터 — 헤더 맨 아래 */}
      <div className="flex">
        <FilterGroup
          options={[{ key: "ALL" as const, label: "전체" }, { key: "KOSPI" as const, label: "KOSPI" }, { key: "KOSDAQ" as const, label: "KOSDAQ" }]}
          value={marketFilter} onChange={setMarketFilter}
        />
      </div>
      </div>
      {/* /필터 영역 */}

      {/* 테이블 + 모바일 카드 */}
      <div className="bg-[var(--bg-card)] rounded-2xl overflow-hidden">
        {/* 데스크톱 테이블 */}
        <div className="hidden md:block overflow-x-auto">
          <table className="w-full text-[13px] sm:text-[14px]">
            <thead>
              <tr className="text-[var(--text-muted)] text-[12px] sm:text-[13px] border-b border-white/[0.06]">
                <th className="text-left px-3 sm:px-5 py-4 font-normal w-8">#</th>
                <th className="text-left px-2 sm:px-3 py-4 font-normal">종목</th>
                <th className="text-left px-2 py-4 font-normal w-14 hidden sm:table-cell">시장</th>
                {hasPer && <th className="text-right px-2 py-4 font-normal hidden md:table-cell">PER</th>}
                <th className="text-right px-2 sm:px-3 py-4 font-normal">외국인</th>
                <th className="text-right px-2 sm:px-3 py-4 font-normal">기관</th>
                <th className="text-right px-2 sm:px-3 py-4 font-normal">{investor === "pension" ? "연기금" : investor === "corp" ? "기타법인" : "합계"}</th>
                <th className="text-right px-2 sm:px-3 py-4 font-normal hidden sm:table-cell">시총대비</th>
                <th className="text-right px-2 sm:px-3 py-4 font-normal">수익률</th>
              </tr>
            </thead>
            <tbody>
              {paged.map((s, i) => {
                const pc = s.price_change?.[displayPeriod];
                const ratio = calcRatio(getInvVal(s, investor, displayPeriod), s.market_cap);
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
                      </div>
                    </td>
                    <td className="px-2 py-2.5 hidden sm:table-cell">
                      <span className={`text-[12px] px-2 py-0.5 rounded-md font-medium ${
                        s.market === "KOSPI" ? "bg-blue-500/10 text-blue-400" : "bg-purple-500/10 text-purple-400"
                      }`}>{s.market}</span>
                    </td>
                    {hasPer && (
                      <td className="px-2 py-2.5 text-right num text-[var(--text-secondary)] hidden md:table-cell">
                        {perLabel(s.per)}
                      </td>
                    )}
                    <td className="px-2 sm:px-3 py-2.5 text-right"><CNum v={s.foreign[displayPeriod]} /></td>
                    <td className="px-2 sm:px-3 py-2.5 text-right"><CNum v={s.institution[displayPeriod]} /></td>
                    <td className="px-2 sm:px-3 py-2.5 text-right font-medium"><CNum v={subjectVal(s, investor, displayPeriod)} /></td>
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
            const inner = (
              <div className="px-4 py-4.5">
                {/* 상단: 순위 + 종목명 + 수익률 */}
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-[var(--text-muted)] num text-[13px] w-5 shrink-0">{page * PAGE_SIZE + i + 1}</span>
                  <span className="text-white font-medium text-[15px] flex-1 truncate">{s.name}</span>
                  {pc != null && (
                    <span className={`text-[13px] font-medium ${pc > 0 ? "positive" : pc < 0 ? "negative" : ""}`}>
                      <span className="num">{pc > 0 ? "+" : ""}{pc.toFixed(1)}%</span>
                    </span>
                  )}
                </div>

                {/* 시장/PER/신호 배지들 */}
                <div className="flex items-center gap-1.5 ml-7 mb-3 flex-wrap">
                  <span className={`text-[11px] px-1.5 py-0.5 rounded font-medium ${
                    s.market === "KOSPI" ? "bg-blue-500/10 text-blue-400" : "bg-purple-500/10 text-purple-400"
                  }`}>{s.market}</span>
                  {hasPer && s.per != null && (
                    <span className="text-[12px] text-[var(--text-muted)]">PER <span className="num">{s.per.toFixed(1)}</span></span>
                  )}
                </div>

                {/* 구분선 */}
                <div className="h-px bg-white/[0.04] mb-3 ml-7" />

                {/* 값 영역 */}
                <div className="ml-7 grid grid-cols-2 gap-y-1.5 gap-x-4 text-[13px]">
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
                    <CNum v={subjectVal(s, investor, displayPeriod)} />
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
