"use client";

/* 섹터·테마 상세의 인터랙티브 부분.

   원래 page.tsx 였다. 그때는 섹터 하나를 보려고 stock-rankings.json 2.6MB 와
   theme-map.json 69KB 를 받아 클라이언트에서 소속 종목을 걸렀다.
   지금은 page.tsx(서버 컴포넌트)가 걸러서 해당 종목만 넘긴다. */

import { useEffect, useState, useMemo, use } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import SectorFundamentals from "../../components/SectorFundamentals";


interface StockRanking {
  name: string; market: string; ticker?: string; sector?: string; sector_mid?: string;
  market_cap?: number | null; per?: number | null; price_change?: Record<string, number>;
  foreign: Record<string, number>; institution: Record<string, number>; combined: Record<string, number>;
  pension?: Record<string, number>;
}
type Investor = "combined" | "foreign" | "institution" | "pension";
type Period = "1d" | "1w" | "1m" | "3m" | "6m";
interface LeaderScore {
  cls: number; tag: "leader" | "emerging" | "follower" | "laggard";
  tagLabel: string; tagColor: string; tagBg: string;
}

function fmtUnit(n: number) {
  const won = n * 1_000_000; const abs = Math.abs(won); const sign = won > 0 ? "+" : "";
  if (abs >= 1e12) return `${sign}${(won / 1e12).toFixed(1)}조원`;
  if (abs >= 1e8) return `${sign}${Math.round(won / 1e8).toLocaleString()}억원`;
  if (abs >= 1e4) return `${sign}${Math.round(won / 1e4).toLocaleString()}만원`;
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
function FilterGroup<T extends string>({ options, value, onChange }: { options: { key: T; label: string }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="flex rounded-xl overflow-hidden border border-white/[0.06] bg-[var(--bg-card)]">
      {options.map((o) => (
        <button key={o.key} onClick={() => onChange(o.key)}
          className={`px-2.5 sm:px-3 py-[5px] sm:py-[7px] text-[12px] sm:text-[13px] transition-all ${value === o.key ? "bg-[var(--accent-blue)] text-white font-medium" : "text-[var(--text-secondary)] hover:text-white hover:bg-white/[0.04]"}`}>{o.label}</button>
      ))}
    </div>
  );
}

function calcLeaderScores(stocks: StockRanking[], period: Period): Map<string, LeaderScore> {
  const scores = new Map<string, LeaderScore>();
  if (stocks.length === 0) return scores;

  const rawData = stocks.map((s) => {
    const flow = s.combined[period] ?? 0;
    const cap = s.market_cap ?? 0;
    const flowIntensity = cap > 0 ? (flow / cap) * 100 : 0;
    const priceMom = s.price_change?.[period] ?? 0;
    const w = s.combined["1w"] ?? 0;
    const m = s.combined["1m"] ?? 0;
    const dailyW = w / 5;
    const dailyM = m / 20;
    const accel = dailyM !== 0 ? dailyW / dailyM : (dailyW > 0 ? 2 : 0);
    return { stock: s, flow, flowIntensity, priceMom, accel };
  });

  const totalPosFlow = rawData.reduce((sum, d) => sum + Math.max(d.flow, 0), 0);

  function pctRank(values: number[], val: number): number {
    const below = values.filter((v) => v < val).length;
    return values.length > 1 ? (below / (values.length - 1)) * 100 : 50;
  }
  const allInt = rawData.map((d) => d.flowIntensity);
  const allMom = rawData.map((d) => d.priceMom);

  const clsArr: { name: string; cls: number; d: typeof rawData[0] }[] = [];
  for (const d of rawData) {
    const share = totalPosFlow > 0 ? (Math.max(d.flow, 0) / totalPosFlow) * 100 : 0;
    const nShare = Math.min(share * 5, 100);
    const nInt = pctRank(allInt, d.flowIntensity);
    const nMom = pctRank(allMom, d.priceMom);
    const nAccel = Math.min(Math.max(d.accel, 0) * 50, 100);
    const cls = d.flow > 0 ? 0.25 * nShare + 0.20 * nInt + 0.35 * nMom + 0.20 * nAccel : 0;
    clsArr.push({ name: d.stock.name, cls, d });
  }

  const posCls = clsArr.filter((c) => c.cls > 0).map((c) => c.cls).sort((a, b) => a - b);
  const p75 = posCls.length > 0 ? posCls[Math.floor(posCls.length * 0.75)] ?? 50 : 50;
  const p50 = posCls.length > 0 ? posCls[Math.floor(posCls.length * 0.50)] ?? 30 : 30;

  for (const c of clsArr) {
    const d = c.d;
    const share = totalPosFlow > 0 ? (Math.max(d.flow, 0) / totalPosFlow) * 100 : 0;
    let tag: LeaderScore["tag"], tagLabel: string, tagColor: string, tagBg: string;
    if (d.flow <= 0) { tag = "laggard"; tagLabel = "소외"; tagColor = "text-[var(--text-muted)]"; tagBg = "bg-white/[0.03]"; }
    else if (c.cls >= p75 && share >= 3) { tag = "leader"; tagLabel = "주도주"; tagColor = "text-amber-400"; tagBg = "bg-amber-500/[0.1]"; }
    else if (c.cls >= p50 && d.accel > 1.2) { tag = "emerging"; tagLabel = "급부상"; tagColor = "text-emerald-400"; tagBg = "bg-emerald-500/[0.1]"; }
    else { tag = "follower"; tagLabel = ""; tagColor = ""; tagBg = ""; }
    scores.set(d.stock.name, { cls: Math.round(c.cls * 10) / 10, tag, tagLabel, tagColor, tagBg });
  }
  return scores;
}

export default function SectorClient({
  sectorName,
  members,
}: {
  sectorName: string;
  /** 이 섹터/테마에 속한 종목. 서버에서 미리 걸러 넘긴다. */
  members: StockRanking[];
}) {
  const router = useRouter();
  const [investor, setInvestor] = useState<Investor>("combined");
  const [period, setPeriod] = useState<Period>("1m");
  const periodLabels: Record<Period, string> = { "1d": "1일", "1w": "1주", "1m": "1개월", "3m": "3개월", "6m": "6개월" };
  const invLabels: Record<Investor, string> = { combined: "외국인+기관", foreign: "외국인", institution: "기관", pension: "연기금" };

  // 소속 판정은 서버가 끝냈다. 여기서는 선택된 투자자·기간으로 정렬만 한다.
  const sectorStocks = useMemo(() => {
    const getVal = (s: StockRanking) =>
      investor === "pension" ? (s.pension?.[period] ?? 0) : (s[investor][period] ?? 0);
    return [...members].sort((a, b) => getVal(b) - getVal(a));
  }, [members, investor, period]);

  const leaderScores = useMemo(() => calcLeaderScores(sectorStocks, period), [sectorStocks, period]);

  const tagCounts = useMemo(() => {
    let leader = 0, emerging = 0, laggard = 0;
    leaderScores.forEach((s) => {
      if (s.tag === "leader") leader++;
      else if (s.tag === "emerging") emerging++;
      else if (s.tag === "laggard" && s.tagLabel) laggard++;
    });
    return { leader, emerging, laggard };
  }, [leaderScores]);


  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <button onClick={() => router.back()} className="text-[var(--text-muted)] hover:text-white transition text-sm">← 섹터 목록</button>
        <div className="w-px h-4 bg-white/10" />
        <h1 className="text-xl sm:text-2xl font-bold">{sectorName}</h1>
        <span className="text-[var(--text-muted)] text-sm num">{sectorStocks.length}종목</span>
      </div>

      {/* 섹터 실적 vs 가격 (펀더멘털) */}
      <SectorFundamentals sectorName={sectorName} />

      <div className="bg-[var(--bg-card)] rounded-2xl p-4 sm:p-6">
        <h3 className="text-xs sm:text-sm font-medium text-[var(--text-secondary)] mb-3">섹터 내 포지션 분석</h3>
        <div className="flex flex-wrap gap-3">
          {[
            { l: "주도주", c: "bg-amber-400", tc: "text-amber-400", n: tagCounts.leader },
            { l: "급부상", c: "bg-emerald-400", tc: "text-emerald-400", n: tagCounts.emerging },
            { l: "소외", c: "bg-white/10", tc: "text-[var(--text-muted)]", n: tagCounts.laggard },
          ].map((d) => (
            <div key={d.l} className="flex items-center gap-1.5">
              <span className={`w-2 h-2 rounded-full ${d.c}`} />
              <span className={`text-[13px] ${d.tc}`}>{d.l}</span>
              <span className="text-[13px] text-white font-semibold num">{d.n}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap gap-2 items-center">
        <select value={investor} onChange={(e) => setInvestor(e.target.value as Investor)}
          className="bg-[var(--bg-card)] rounded-lg px-2.5 py-[5px] text-[12px] sm:text-[13px] text-[var(--text-secondary)] outline-none cursor-pointer">
          {Object.entries(invLabels).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <FilterGroup options={Object.entries(periodLabels).map(([k, v]) => ({ key: k as Period, label: v }))} value={period} onChange={setPeriod} />
      </div>

      <div className="bg-[var(--bg-card)] rounded-2xl overflow-hidden">
        <div className="flex items-center text-[var(--text-muted)] text-[12px] sm:text-[13px] border-b border-white/[0.06] px-3 sm:px-5 py-4">
          <span className="w-8 shrink-0 hidden sm:block">#</span>
          <span className="flex-1 min-w-0">종목</span>
          <span className="w-14 text-left hidden sm:block">시장</span>
          <span className="w-16 sm:w-24 text-right shrink-0">외국인</span>
          <span className="w-16 sm:w-24 text-right shrink-0">기관</span>
          <span className="w-16 sm:w-24 text-right shrink-0">{investor === "pension" ? "연기금" : "합계"}</span>
          <span className="w-14 text-right shrink-0 hidden sm:block">주가</span>
        </div>
        {sectorStocks.map((s, i) => {
          const score = leaderScores.get(s.name);
          const pc = s.price_change?.[period];
          return (
            <div key={s.name} className="flex items-center px-3 sm:px-5 py-2.5 border-t border-white/[0.03] hover:bg-white/[0.02] transition">
              <span className="w-8 shrink-0 text-[var(--text-muted)] num text-xs hidden sm:block">{i + 1}</span>
              <div className="flex-1 min-w-0 flex items-center gap-1.5">
                {s.ticker ? (
                  <Link href={`/stocks/${s.ticker}`} className="text-white text-[13px] sm:text-[14px] font-medium hover:text-[var(--accent-blue)] transition truncate">{s.name}</Link>
                ) : <span className="text-white text-[13px] sm:text-[14px] font-medium truncate">{s.name}</span>}
                {score && score.tagLabel && (
                  <span className={`text-[11px] px-1.5 py-0.5 rounded-md shrink-0 ${score.tagBg} ${score.tagColor}`}>{score.tagLabel}</span>
                )}
              </div>
              <span className="w-14 hidden sm:block">
                <span className={`text-[12px] px-2 py-0.5 rounded-md font-medium ${s.market === "KOSPI" ? "bg-blue-500/10 text-blue-400" : "bg-purple-500/10 text-purple-400"}`}>{s.market}</span>
              </span>
              <span className="w-16 sm:w-24 text-right shrink-0 text-[13px] sm:text-[14px]"><CNum v={s.foreign[period]} /></span>
              <span className="w-16 sm:w-24 text-right shrink-0 text-[13px] sm:text-[14px]"><CNum v={s.institution[period]} /></span>
              <span className="w-16 sm:w-24 text-right shrink-0 text-[13px] sm:text-[14px] font-medium"><CNum v={investor === "pension" ? (s.pension?.[period] ?? 0) : s.combined[period]} /></span>
              <span className="w-14 text-right shrink-0 hidden sm:block">
                {pc != null ? <span className={`num text-xs ${pc > 0 ? "positive" : pc < 0 ? "negative" : ""}`}>{pc > 0 ? "+" : ""}{pc.toFixed(1)}%</span> : <span className="text-[var(--text-muted)]">-</span>}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
