"use client";

import { useEffect, useMemo, useState, Suspense } from "react";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";

export const dynamic = "force-static";

/* ── 타입 ─────────────────────────────────────── */
interface StockRanking {
  name: string;
  market: string;
  ticker?: string;
  sector?: string;
  sector_mid?: string;
  market_cap?: number | null;
  per?: number | null;
  price_change?: Record<string, number>;
  foreign: Record<string, number>;
  institution: Record<string, number>;
  combined: Record<string, number>;
  pension?: Record<string, number>;
}

type Period = "1d" | "1w" | "1m" | "3m" | "6m";

interface Filters {
  market: "ALL" | "KOSPI" | "KOSDAQ";
  period: Period;
  minMarketCap: number;       // 억원 단위
  minForeign: number;         // 억원 단위 (해당 기간 누적)
  minInst: number;            // 억원 단위
  minPension: number;         // 억원 단위
  minPriceMom: number;        // % (해당 기간)
  maxPer: number | null;      // null = 제한 없음
  excludeSpac: boolean;
  sortBy: "combined" | "foreign" | "inst" | "pension" | "market_cap" | "price_mom";
  sortDir: "desc" | "asc";
}

const DEFAULT_FILTERS: Filters = {
  market: "ALL",
  period: "1m",
  minMarketCap: 0,
  minForeign: 0,
  minInst: 0,
  minPension: 0,
  minPriceMom: -100,
  maxPer: null,
  excludeSpac: true,
  sortBy: "combined",
  sortDir: "desc",
};

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
function CNum({ v }: { v: number | null }) {
  if (v == null) return <span className="num text-[var(--text-muted)]">-</span>;
  const cls = v > 0 ? "positive" : v < 0 ? "negative" : "text-[var(--text-secondary)]";
  const str = fmtUnit(v);
  const m = str.match(/^(.+?)([가-힣]+)$/);
  return m ? (
    <span className={cls}>
      <span className="num">{m[1]}</span>
      {m[2]}
    </span>
  ) : (
    <span className={`num ${cls}`}>{str}</span>
  );
}

const periodLabels: Record<Period, string> = {
  "1d": "1일",
  "1w": "1주",
  "1m": "1개월",
  "3m": "3개월",
  "6m": "6개월",
};

/* ── 메인 ─────────────────────────────────────── */
function ScreenerInner() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const [allStocks, setAllStocks] = useState<StockRanking[]>([]);
  const [meta, setMeta] = useState<{ date?: string } | null>(null);
  const [loading, setLoading] = useState(true);

  // URL에서 필터 초기값 읽기
  const [filters, setFilters] = useState<Filters>(() => {
    const f = { ...DEFAULT_FILTERS };
    const market = searchParams.get("m");
    if (market === "KOSPI" || market === "KOSDAQ" || market === "ALL") f.market = market;
    const period = searchParams.get("p");
    if (period === "1d" || period === "1w" || period === "1m" || period === "3m" || period === "6m") f.period = period;
    const n = (k: string) => {
      const v = searchParams.get(k);
      return v != null ? Number(v) : null;
    };
    if (n("mc") != null) f.minMarketCap = n("mc")!;
    if (n("f") != null) f.minForeign = n("f")!;
    if (n("i") != null) f.minInst = n("i")!;
    if (n("ps") != null) f.minPension = n("ps")!;
    if (n("pm") != null) f.minPriceMom = n("pm")!;
    if (n("per") != null) f.maxPer = n("per");
    const sb = searchParams.get("sb");
    if (sb === "combined" || sb === "foreign" || sb === "inst" || sb === "pension" || sb === "market_cap" || sb === "price_mom") f.sortBy = sb;
    const sd = searchParams.get("sd");
    if (sd === "desc" || sd === "asc") f.sortDir = sd;
    return f;
  });

  useEffect(() => {
    Promise.all([
      fetch("/data/stock-rankings.json").then((r) => r.json()),
      fetch("/data/meta.json").then((r) => r.json()).catch(() => null),
    ])
      .then(([s, m]) => {
        setAllStocks(s.data);
        setMeta(m);
      })
      .finally(() => setLoading(false));
  }, []);

  // URL 동기화
  function updateFilter<K extends keyof Filters>(key: K, value: Filters[K]) {
    const next = { ...filters, [key]: value };
    setFilters(next);
    syncUrl(next);
  }

  function syncUrl(f: Filters) {
    const params = new URLSearchParams();
    if (f.market !== DEFAULT_FILTERS.market) params.set("m", f.market);
    if (f.period !== DEFAULT_FILTERS.period) params.set("p", f.period);
    if (f.minMarketCap !== DEFAULT_FILTERS.minMarketCap) params.set("mc", String(f.minMarketCap));
    if (f.minForeign !== DEFAULT_FILTERS.minForeign) params.set("f", String(f.minForeign));
    if (f.minInst !== DEFAULT_FILTERS.minInst) params.set("i", String(f.minInst));
    if (f.minPension !== DEFAULT_FILTERS.minPension) params.set("ps", String(f.minPension));
    if (f.minPriceMom !== DEFAULT_FILTERS.minPriceMom) params.set("pm", String(f.minPriceMom));
    if (f.maxPer != null) params.set("per", String(f.maxPer));
    if (f.sortBy !== DEFAULT_FILTERS.sortBy) params.set("sb", f.sortBy);
    if (f.sortDir !== DEFAULT_FILTERS.sortDir) params.set("sd", f.sortDir);
    const qs = params.toString();
    window.history.replaceState(null, "", `/screener${qs ? `?${qs}` : ""}`);
  }

  function resetFilters() {
    setFilters(DEFAULT_FILTERS);
    window.history.replaceState(null, "", "/screener");
  }

  function applyPreset(preset: "longterm" | "shortterm" | "value" | "pension") {
    let next: Filters;
    if (preset === "longterm") {
      next = {
        ...DEFAULT_FILTERS,
        period: "3m",
        minMarketCap: 500,
        minForeign: 50,
        minInst: 50,
        minPension: 20,
        minPriceMom: 0,
      };
    } else if (preset === "shortterm") {
      next = {
        ...DEFAULT_FILTERS,
        period: "1m",
        minMarketCap: 500,
        minForeign: 50,
        minInst: 50,
        minPriceMom: 0,
      };
    } else if (preset === "value") {
      next = {
        ...DEFAULT_FILTERS,
        period: "3m",
        minMarketCap: 1000,
        minForeign: 30,
        maxPer: 15,
      };
    } else {
      // pension
      next = {
        ...DEFAULT_FILTERS,
        period: "3m",
        minMarketCap: 500,
        minPension: 30,
        minPriceMom: 0,
      };
    }
    setFilters(next);
    syncUrl(next);
  }

  // 필터링
  const filtered = useMemo(() => {
    if (!allStocks.length) return [];
    const f = filters;
    const p = f.period;

    return allStocks.filter((s) => {
      // 시장
      if (f.market !== "ALL" && s.market !== f.market) return false;
      // 스팩 제외
      if (f.excludeSpac && (s.name.includes("스팩") || s.name.includes("SPAC"))) return false;
      // 시총 (단위: 억원, market_cap도 동일 단위)
      if (f.minMarketCap > 0 && (s.market_cap ?? 0) < f.minMarketCap) return false;
      // 외국인 (combined 단위는 백만원, 사용자 입력은 억원 → 100배 변환)
      const fVal = s.foreign[p] ?? 0;
      if (f.minForeign > 0 && fVal < f.minForeign * 100) return false;
      // 기관
      const iVal = s.institution[p] ?? 0;
      if (f.minInst > 0 && iVal < f.minInst * 100) return false;
      // 연기금
      const psVal = s.pension?.[p] ?? 0;
      if (f.minPension > 0 && psVal < f.minPension * 100) return false;
      // 가격 모멘텀
      const pm = s.price_change?.[p] ?? 0;
      if (pm < f.minPriceMom) return false;
      // PER
      if (f.maxPer != null && (s.per == null || s.per > f.maxPer)) return false;
      return true;
    }).sort((a, b) => {
      const get = (s: StockRanking) => {
        switch (f.sortBy) {
          case "combined": return s.combined[p] ?? 0;
          case "foreign": return s.foreign[p] ?? 0;
          case "inst": return s.institution[p] ?? 0;
          case "pension": return s.pension?.[p] ?? 0;
          case "market_cap": return s.market_cap ?? 0;
          case "price_mom": return s.price_change?.[p] ?? 0;
        }
      };
      const av = get(a), bv = get(b);
      return f.sortDir === "desc" ? bv - av : av - bv;
    });
  }, [allStocks, filters]);

  const PAGE_SIZE = 50;
  const [page, setPage] = useState(0);
  useEffect(() => setPage(0), [filters]);
  const paged = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-6 w-48 bg-white/[0.04] rounded animate-pulse" />
        <div className="h-40 bg-white/[0.04] rounded animate-pulse" />
        <div className="h-96 bg-white/[0.04] rounded animate-pulse" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* 헤더 */}
      <div className="flex items-baseline justify-between gap-2">
        <div>
          <h2 className="text-[16px] sm:text-[18px] font-semibold text-white">스크리너</h2>
          <p className="text-[11px] text-[var(--text-muted)] mt-0.5">
            조건을 직접 설정해서 종목을 발굴하세요. KRX 공시 데이터 기반.
          </p>
        </div>
        {meta?.date && (
          <span className="text-[10px] text-[var(--text-muted)] num shrink-0">{meta.date} 기준</span>
        )}
      </div>

      {/* 프리셋 (시작점 제공) */}
      <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-3 sm:p-4">
        <div className="flex items-baseline justify-between mb-2">
          <span className="text-[11px] sm:text-[12px] font-medium text-[var(--text-secondary)]">조건 프리셋 (시작값, 자유롭게 수정 가능)</span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <button onClick={() => applyPreset("longterm")} className="px-3 py-1.5 rounded-lg bg-indigo-500/15 text-indigo-400 hover:bg-indigo-500/25 transition text-[11px]">
            장기 보유 후보
          </button>
          <button onClick={() => applyPreset("shortterm")} className="px-3 py-1.5 rounded-lg bg-rose-500/15 text-rose-400 hover:bg-rose-500/25 transition text-[11px]">
            단기 모멘텀
          </button>
          <button onClick={() => applyPreset("value")} className="px-3 py-1.5 rounded-lg bg-emerald-500/15 text-emerald-400 hover:bg-emerald-500/25 transition text-[11px]">
            저PER + 매수세
          </button>
          <button onClick={() => applyPreset("pension")} className="px-3 py-1.5 rounded-lg bg-amber-500/15 text-amber-400 hover:bg-amber-500/25 transition text-[11px]">
            연기금 매집
          </button>
          <button onClick={resetFilters} className="px-3 py-1.5 rounded-lg bg-white/[0.04] text-[var(--text-secondary)] hover:bg-white/[0.08] transition text-[11px] ml-auto">
            초기화
          </button>
        </div>
      </div>

      {/* 조건 입력 */}
      <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-3 sm:p-4 space-y-3">
        <span className="text-[11px] sm:text-[12px] font-medium text-[var(--text-secondary)]">검색 조건</span>

        {/* 1행: 시장 / 기간 */}
        <div className="grid grid-cols-2 gap-2">
          <div>
            <label className="block text-[10px] text-[var(--text-muted)] mb-1">시장</label>
            <select
              value={filters.market}
              onChange={(e) => updateFilter("market", e.target.value as Filters["market"])}
              className="w-full bg-white/[0.04] border border-white/[0.06] rounded-lg px-2 py-1.5 text-[12px] text-white outline-none focus:border-[var(--accent-blue)]"
            >
              <option value="ALL">전체</option>
              <option value="KOSPI">KOSPI</option>
              <option value="KOSDAQ">KOSDAQ</option>
            </select>
          </div>
          <div>
            <label className="block text-[10px] text-[var(--text-muted)] mb-1">기간</label>
            <select
              value={filters.period}
              onChange={(e) => updateFilter("period", e.target.value as Period)}
              className="w-full bg-white/[0.04] border border-white/[0.06] rounded-lg px-2 py-1.5 text-[12px] text-white outline-none focus:border-[var(--accent-blue)]"
            >
              <option value="1d">1일</option>
              <option value="1w">1주</option>
              <option value="1m">1개월</option>
              <option value="3m">3개월</option>
              <option value="6m">6개월</option>
            </select>
          </div>
        </div>

        {/* 2행: 시총 / 가격 모멘텀 */}
        <div className="grid grid-cols-2 gap-2">
          <NumInput
            label="시가총액 최소 (억원)"
            value={filters.minMarketCap}
            onChange={(v) => updateFilter("minMarketCap", v)}
            placeholder="예: 1000"
          />
          <NumInput
            label={`가격 ${periodLabels[filters.period]} 모멘텀 최소 (%)`}
            value={filters.minPriceMom}
            onChange={(v) => updateFilter("minPriceMom", v)}
            placeholder="예: 0 (=상승), -10 (=10%이내 하락)"
            allowNegative
          />
        </div>

        {/* 3행: 외인 / 기관 */}
        <div className="grid grid-cols-2 gap-2">
          <NumInput
            label={`외국인 ${periodLabels[filters.period]} 순매수 최소 (억원)`}
            value={filters.minForeign}
            onChange={(v) => updateFilter("minForeign", v)}
            placeholder="예: 50"
          />
          <NumInput
            label={`기관 ${periodLabels[filters.period]} 순매수 최소 (억원)`}
            value={filters.minInst}
            onChange={(v) => updateFilter("minInst", v)}
            placeholder="예: 50"
          />
        </div>

        {/* 4행: 연기금 / PER */}
        <div className="grid grid-cols-2 gap-2">
          <NumInput
            label={`연기금 ${periodLabels[filters.period]} 순매수 최소 (억원)`}
            value={filters.minPension}
            onChange={(v) => updateFilter("minPension", v)}
            placeholder="예: 20"
          />
          <NumInput
            label="PER 최대 (선택)"
            value={filters.maxPer ?? ("" as unknown as number)}
            onChange={(v) => updateFilter("maxPer", v === ("" as unknown as number) || isNaN(v as number) ? null : v)}
            placeholder="예: 15 (저PER만)"
          />
        </div>

        {/* 정렬 옵션 */}
        <div className="grid grid-cols-2 gap-2 pt-1">
          <div>
            <label className="block text-[10px] text-[var(--text-muted)] mb-1">정렬 기준</label>
            <select
              value={filters.sortBy}
              onChange={(e) => updateFilter("sortBy", e.target.value as Filters["sortBy"])}
              className="w-full bg-white/[0.04] border border-white/[0.06] rounded-lg px-2 py-1.5 text-[12px] text-white outline-none focus:border-[var(--accent-blue)]"
            >
              <option value="combined">외인+기관 합계</option>
              <option value="foreign">외국인 순매수</option>
              <option value="inst">기관 순매수</option>
              <option value="pension">연기금 순매수</option>
              <option value="market_cap">시가총액</option>
              <option value="price_mom">가격 모멘텀</option>
            </select>
          </div>
          <div>
            <label className="block text-[10px] text-[var(--text-muted)] mb-1">정렬 방향</label>
            <select
              value={filters.sortDir}
              onChange={(e) => updateFilter("sortDir", e.target.value as Filters["sortDir"])}
              className="w-full bg-white/[0.04] border border-white/[0.06] rounded-lg px-2 py-1.5 text-[12px] text-white outline-none focus:border-[var(--accent-blue)]"
            >
              <option value="desc">큰 순서</option>
              <option value="asc">작은 순서</option>
            </select>
          </div>
        </div>
      </div>

      {/* 결과 */}
      <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl">
        <div className="px-3 sm:px-4 py-3 border-b border-white/[0.06] flex items-baseline justify-between">
          <h3 className="text-[13px] sm:text-[14px] font-semibold text-white">
            검색 결과 <span className="num text-[var(--text-secondary)] font-normal">{filtered.length.toLocaleString()}</span>
            <span className="text-[11px] text-[var(--text-muted)] font-normal ml-1">종목</span>
          </h3>
          {totalPages > 1 && (
            <span className="text-[10px] text-[var(--text-muted)] num">{page + 1} / {totalPages}</span>
          )}
        </div>

        {/* 데스크톱 테이블 */}
        <div className="hidden md:block overflow-x-auto">
          <table className="w-full text-[12px] sm:text-[13px]">
            <thead>
              <tr className="text-[var(--text-muted)] text-[10px] sm:text-[11px] border-b border-white/[0.06]">
                <th className="text-left px-3 sm:px-5 py-3 font-normal w-8">#</th>
                <th className="text-left px-2 sm:px-3 py-3 font-normal">종목</th>
                <th className="text-left px-2 py-3 font-normal w-14">시장</th>
                <th className="text-right px-2 py-3 font-normal">PER</th>
                <th className="text-right px-2 sm:px-3 py-3 font-normal">시가총액</th>
                <th className="text-right px-2 sm:px-3 py-3 font-normal">외국인 ({periodLabels[filters.period]})</th>
                <th className="text-right px-2 sm:px-3 py-3 font-normal">기관 ({periodLabels[filters.period]})</th>
                <th className="text-right px-2 sm:px-3 py-3 font-normal">연기금 ({periodLabels[filters.period]})</th>
                <th className="text-right px-2 sm:px-3 py-3 font-normal">합계 ({periodLabels[filters.period]})</th>
                <th className="text-right px-2 sm:px-3 py-3 font-normal">가격 ({periodLabels[filters.period]})</th>
              </tr>
            </thead>
            <tbody>
              {paged.map((s, i) => {
                const pm = s.price_change?.[filters.period];
                return (
                  <tr key={s.name} className="border-t border-white/[0.03] hover:bg-white/[0.02] transition">
                    <td className="px-3 sm:px-5 py-2.5 text-[var(--text-muted)] num text-xs">{page * PAGE_SIZE + i + 1}</td>
                    <td className="px-2 sm:px-3 py-2.5">
                      {s.ticker ? (
                        <Link href={`/stocks/${s.ticker}`} className="text-white font-medium hover:text-[var(--accent-blue)] transition">
                          {s.name}
                        </Link>
                      ) : (
                        <span className="text-white font-medium">{s.name}</span>
                      )}
                    </td>
                    <td className="px-2 py-2.5">
                      <span className={`text-[10px] px-2 py-0.5 rounded-md font-medium ${
                        s.market === "KOSPI" ? "bg-blue-500/10 text-blue-400" : "bg-purple-500/10 text-purple-400"
                      }`}>{s.market}</span>
                    </td>
                    <td className="px-2 py-2.5 text-right num text-[var(--text-secondary)]">
                      {s.per != null ? s.per.toFixed(1) : "-"}
                    </td>
                    <td className="px-2 sm:px-3 py-2.5 text-right num text-[var(--text-secondary)]">
                      {s.market_cap != null ? `${s.market_cap.toLocaleString()}억` : "-"}
                    </td>
                    <td className="px-2 sm:px-3 py-2.5 text-right"><CNum v={s.foreign[filters.period]} /></td>
                    <td className="px-2 sm:px-3 py-2.5 text-right"><CNum v={s.institution[filters.period]} /></td>
                    <td className="px-2 sm:px-3 py-2.5 text-right"><CNum v={s.pension?.[filters.period] ?? null} /></td>
                    <td className="px-2 sm:px-3 py-2.5 text-right font-medium"><CNum v={s.combined[filters.period]} /></td>
                    <td className="px-2 sm:px-3 py-2.5 text-right">
                      {pm != null ? (
                        <span className={`num text-xs ${pm > 0 ? "positive" : pm < 0 ? "negative" : ""}`}>
                          {pm > 0 ? "+" : ""}{pm.toFixed(1)}%
                        </span>
                      ) : <span className="text-[var(--text-muted)]">-</span>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* 모바일 카드 */}
        <div className="md:hidden divide-y divide-white/[0.04]">
          {paged.map((s, i) => {
            const pm = s.price_change?.[filters.period];
            const inner = (
              <div className="px-4 py-3">
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="text-[var(--text-muted)] num text-[11px] w-5 shrink-0">{page * PAGE_SIZE + i + 1}</span>
                  <span className="text-white font-medium text-[14px] flex-1 truncate">{s.name}</span>
                  <span className={`text-[10px] px-1.5 py-0.5 rounded-md font-medium shrink-0 ${
                    s.market === "KOSPI" ? "bg-blue-500/10 text-blue-400" : "bg-purple-500/10 text-purple-400"
                  }`}>{s.market}</span>
                </div>
                <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11px] pl-7">
                  <div className="flex justify-between">
                    <span className="text-[var(--text-muted)]">합계</span>
                    <CNum v={s.combined[filters.period]} />
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[var(--text-muted)]">가격</span>
                    {pm != null ? (
                      <span className={`num ${pm > 0 ? "positive" : pm < 0 ? "negative" : ""}`}>
                        {pm > 0 ? "+" : ""}{pm.toFixed(1)}%
                      </span>
                    ) : <span className="text-[var(--text-muted)]">-</span>}
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[var(--text-muted)]">외국인</span>
                    <CNum v={s.foreign[filters.period]} />
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[var(--text-muted)]">기관</span>
                    <CNum v={s.institution[filters.period]} />
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[var(--text-muted)]">연기금</span>
                    <CNum v={s.pension?.[filters.period] ?? null} />
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[var(--text-muted)]">시총</span>
                    <span className="num text-[var(--text-secondary)]">
                      {s.market_cap != null ? `${s.market_cap.toLocaleString()}억` : "-"}
                    </span>
                  </div>
                </div>
              </div>
            );
            return s.ticker ? (
              <Link key={s.name} href={`/stocks/${s.ticker}`} className="block hover:bg-white/[0.02] transition">
                {inner}
              </Link>
            ) : (
              <div key={s.name}>{inner}</div>
            );
          })}
        </div>

        {filtered.length === 0 && (
          <div className="px-4 py-12 text-center text-[var(--text-muted)] text-[12px]">
            조건에 맞는 종목이 없습니다. 조건을 완화해보세요.
          </div>
        )}

        {/* 페이징 */}
        {totalPages > 1 && (
          <div className="flex items-center justify-center gap-1 p-3 border-t border-white/[0.06]">
            <button
              onClick={() => setPage(Math.max(0, page - 1))}
              disabled={page === 0}
              className="px-3 py-1.5 rounded-lg text-[11px] bg-white/[0.04] text-[var(--text-secondary)] hover:bg-white/[0.08] disabled:opacity-30 disabled:cursor-not-allowed transition"
            >
              이전
            </button>
            <span className="text-[11px] text-[var(--text-muted)] px-2 num">
              {page + 1} / {totalPages}
            </span>
            <button
              onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
              disabled={page >= totalPages - 1}
              className="px-3 py-1.5 rounded-lg text-[11px] bg-white/[0.04] text-[var(--text-secondary)] hover:bg-white/[0.08] disabled:opacity-30 disabled:cursor-not-allowed transition"
            >
              다음
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── 숫자 입력 컴포넌트 ─────────────────────────── */
function NumInput({ label, value, onChange, placeholder, allowNegative = false }: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  placeholder?: string;
  allowNegative?: boolean;
}) {
  const [text, setText] = useState(value === DEFAULT_FILTERS.minPriceMom && allowNegative ? "" : value === 0 ? "" : String(value));
  useEffect(() => {
    setText(value === DEFAULT_FILTERS.minPriceMom && allowNegative ? "" : value === 0 ? "" : String(value));
  }, [value, allowNegative]);
  return (
    <div>
      <label className="block text-[10px] text-[var(--text-muted)] mb-1">{label}</label>
      <input
        type="text"
        inputMode="decimal"
        value={text}
        placeholder={placeholder}
        onChange={(e) => {
          const v = e.target.value;
          // 빈 입력 → default
          if (v === "" || v === "-") {
            setText(v);
            onChange(allowNegative ? -100 : 0);
            return;
          }
          // 숫자만 허용
          const re = allowNegative ? /^-?\d*\.?\d*$/ : /^\d*\.?\d*$/;
          if (!re.test(v)) return;
          setText(v);
          const n = parseFloat(v);
          if (!isNaN(n)) onChange(n);
        }}
        className="w-full bg-white/[0.04] border border-white/[0.06] rounded-lg px-2 py-1.5 text-[12px] text-white outline-none focus:border-[var(--accent-blue)] num"
      />
    </div>
  );
}

export default function ScreenerPage() {
  return (
    <Suspense fallback={<div className="h-96 bg-white/[0.04] rounded animate-pulse" />}>
      <ScreenerInner />
    </Suspense>
  );
}
