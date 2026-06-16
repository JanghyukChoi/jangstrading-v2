"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import {
  Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
} from "recharts";

export const dynamic = "force-static";

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
  sector?: string;
  sector_mid?: string;
  market_cap?: number | null;
  price_change?: Record<string, number>;
  foreign: Record<string, number>;
  institution: Record<string, number>;
  combined: Record<string, number>;
  pension?: Record<string, number>;
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
  const str = fmtUnit(v);
  const m = str.match(/^(.+?)([가-힣]+)$/);
  return m ? (
    <span className={cls}><span className="num">{m[1]}</span>{m[2]}{suffix}</span>
  ) : (
    <span className={`num ${cls}`}>{str}{suffix}</span>
  );
}
// 한글 단위(억원·만원·조원·원)는 .num에서 빼서 Pretendard로 렌더
function NumUnit({ v, cls = "" }: { v: number; cls?: string }) {
  const str = fmtUnit(v);
  const m = str.match(/^(.+?)([가-힣]+)$/);
  return m ? (
    <span className={cls}><span className="num">{m[1]}</span>{m[2]}</span>
  ) : (
    <span className={`num ${cls}`}>{str}</span>
  );
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

      {/* 해석 */}
      <p className="text-[11px] text-[var(--text-secondary)] mt-4 leading-relaxed border-t border-white/[0.04] pt-3">
        💡 {(() => {
          const buyPct = total > 0 ? bothBuy / total * 100 : 0;
          const sellPct = total > 0 ? bothSell / total * 100 : 0;
          if (buyPct > sellPct && buyPct > 35) return `외국인과 기관이 동시에 매수하는 종목이 ${bothBuy}개로, 시장 전반에 매수 합의가 형성되고 있습니다. 두 투자 주체가 같은 방향으로 움직일 때 추세가 강해지는 경향이 있습니다.`;
          if (sellPct > buyPct && sellPct > 35) return `외국인과 기관이 동시에 매도하는 종목이 ${bothSell}개로, 시장 전반에 매도 압력이 강합니다. 양쪽 모두 빠져나가는 구간에서는 방어적 포지션이 유리할 수 있습니다.`;
          return `외국인과 기관의 방향이 엇갈린 종목이 ${mixed}개(${total > 0 ? (mixed / total * 100).toFixed(0) : 0}%)로, 두 주체의 시각이 갈리고 있습니다. 이런 구간에서는 한쪽의 방향이 확정될 때까지 관망하거나, 엇갈림 속에서 기회를 찾을 수 있습니다.`;
        })()}
      </p>
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

      {/* 해석 */}
      <p className="text-[11px] text-[var(--text-secondary)] mt-3 leading-relaxed border-t border-white/[0.04] pt-3">
        💡 {pct >= 70
          ? `${pct}%는 높은 집중도입니다. ${investorKey === "foreign" ? "외국인" : "기관"}이 소수 종목에 확신을 갖고 집중 매수 중입니다.`
          : pct >= 40
          ? `${pct}%는 보통 수준입니다. ${investorKey === "foreign" ? "외국인" : "기관"}이 특정 종목과 시장 전체를 혼합하여 매수 중입니다.`
          : `${pct}%는 낮은 집중도입니다. ${investorKey === "foreign" ? "외국인" : "기관"}이 시장 전체에 분산 매수 중이며, 인덱스 추종 가능성이 높습니다.`
        }
      </p>
    </div>
  );
}

/* ── 오늘의 주목 ────────────────────────────── */
function TodayHighlight({ stocks }: { stocks: StockRanking[] }) {
  const data = useMemo(() => {
    // 사용할 기간 결정 (1m → 3m 폴백)
    function pickPeriod(checkFn: (p: string) => boolean): string {
      return checkFn("1m") ? "1m" : "3m";
    }

    // ── 1. 주도 섹터 & 주도주 ──
    function getSectorLeaders(period: string) {
      const map: Record<string, { stocks: StockRanking[]; total: number }> = {};
      for (const s of stocks) {
        const mid = s.sector_mid;
        if (!mid || mid === "기타") continue;
        if (!map[mid]) map[mid] = { stocks: [], total: 0 };
        map[mid].stocks.push(s);
        map[mid].total += s.combined[period] ?? 0;
      }

      const top3 = Object.entries(map)
        .sort((a, b) => b[1].total - a[1].total)
        .slice(0, 3);

      return top3.map(([name, d]) => {
        const sectorStocks = d.stocks;
        const totalPosFlow = sectorStocks.reduce((sum, s) => sum + Math.max(s.combined[period] ?? 0, 0), 0);

        function pctRank(values: number[], val: number): number {
          const below = values.filter((v) => v < val).length;
          return values.length > 1 ? (below / (values.length - 1)) * 100 : 50;
        }

        const rawData = sectorStocks.map((s) => {
          const flow = s.combined[period] ?? 0;
          const cap = s.market_cap ?? 0;
          const intensity = cap > 0 ? (flow / cap) * 100 : 0;
          const mom = s.price_change?.[period] ?? 0;
          const dw = (s.combined["1w"] ?? 0) / 5;
          const dm = (s.combined["1m"] ?? 0) / 20;
          const accel = dm !== 0 ? dw / dm : (dw > 0 ? 2 : 0);
          const share = totalPosFlow > 0 ? (Math.max(flow, 0) / totalPosFlow) * 100 : 0;
          return { stock: s, flow, intensity, mom, accel, share };
        });

        const allInt = rawData.map((d) => d.intensity);
        const allMom = rawData.map((d) => d.mom);

        const scored = rawData.map((d) => {
          const nShare = Math.min(d.share * 5, 100);
          const nInt = pctRank(allInt, d.intensity);
          const nMom = pctRank(allMom, d.mom);
          const nAccel = Math.min(Math.max(d.accel, 0) * 50, 100);
          const cls = d.flow > 0 ? 0.25 * nShare + 0.20 * nInt + 0.35 * nMom + 0.20 * nAccel : 0;
          return { ...d, cls };
        });

        const posCls = scored.filter((s) => s.cls > 0).map((s) => s.cls).sort((a, b) => a - b);
        const p75 = posCls.length > 0 ? posCls[Math.floor(posCls.length * 0.75)] ?? 50 : 50;

        // 주도주 중 시총 상위 3개
        const leaders = scored
          .filter((s) => s.cls >= p75 && s.share >= 3)
          .sort((a, b) => (b.stock.market_cap ?? 0) - (a.stock.market_cap ?? 0))
          .slice(0, 3)
          .map((s) => s.stock);

        return { name, total: d.total, leaders };
      }).filter((s) => s.leaders.length > 0);
    }

    let sectorLeaders = getSectorLeaders("1m");
    const sectorPeriod = sectorLeaders.length > 0 ? "1m" : "3m";
    if (sectorLeaders.length === 0) sectorLeaders = getSectorLeaders("3m");

    // ── 2. 연기금 집중 ──
    function getPensionTop(period: string) {
      return stocks
        .filter((s) => (s.pension?.[period] ?? 0) > 0)
        .sort((a, b) => (b.pension?.[period] ?? 0) - (a.pension?.[period] ?? 0))
        .slice(0, 3);
    }

    let pensionTop = getPensionTop("1m");
    const pensionPeriod = pensionTop.length > 0 ? "1m" : "3m";
    if (pensionTop.length === 0) pensionTop = getPensionTop("3m");

    return { sectorLeaders, sectorPeriod, pensionTop, pensionPeriod };
  }, [stocks]);

  if (data.sectorLeaders.length === 0 && data.pensionTop.length === 0) return null;

  const periodLabel = (p: string) => p === "1m" ? "1개월" : "3개월";

  return (
    <>
      {/* 주도 섹터 & 주도주 */}
      {data.sectorLeaders.length > 0 && (
        <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-4 sm:p-6">
          <div className="flex items-baseline gap-2 mb-3">
            <h4 className="text-[13px] sm:text-[14px] font-semibold text-white">주도 섹터 & 주도주</h4>
            <span className="text-[10px] text-[var(--text-muted)]">{periodLabel(data.sectorPeriod)} 기준</span>
          </div>
          <div className="space-y-3">
            {data.sectorLeaders.map((s) => (
              <div key={s.name}>
                <Link href={`/sectors/${encodeURIComponent(s.name)}`} className="flex items-center gap-2 mb-1.5 group">
                  <span className="text-[12px] sm:text-[13px] text-[var(--text-secondary)] font-medium group-hover:text-[var(--accent-blue)] transition">{s.name}</span>
                  <NumUnit v={s.total} cls="text-[11px] positive" />
                  <svg width="10" height="10" viewBox="0 0 16 16" fill="currentColor" className="text-[var(--text-muted)]"><path d="M6.22 3.22a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06l-4.25 4.25a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042L9.94 8 6.22 4.28a.75.75 0 0 1 0-1.06Z"/></svg>
                </Link>
                <div className="flex flex-wrap gap-1.5">
                  {s.leaders.map((st) => (
                    <Link key={st.name} href={st.ticker ? `/stocks/${st.ticker}` : "#"}
                      className="inline-flex items-center px-2.5 py-1.5 rounded-lg bg-white/[0.04] border border-white/[0.08] hover:border-white/[0.15] transition text-[11px] sm:text-[12px]">
                      <span className="text-white font-medium">{st.name}</span>
                    </Link>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 연기금 집중 */}
      {data.pensionTop.length > 0 && (
        <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-4 sm:p-6">
          <div className="flex items-baseline gap-2 mb-3">
            <h4 className="text-[13px] sm:text-[14px] font-semibold text-white">연기금 집중</h4>
            <span className="text-[10px] text-[var(--text-muted)]">{periodLabel(data.pensionPeriod)} 순매수</span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {data.pensionTop.map((s) => (
              <Link key={s.name} href={s.ticker ? `/stocks/${s.ticker}` : "#"}
                className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-white/[0.04] border border-white/[0.08] hover:border-white/[0.15] transition text-[11px] sm:text-[12px]">
                <span className="text-white font-medium">{s.name}</span>
                <NumUnit v={s.pension?.[data.pensionPeriod] ?? 0} cls="text-[10px] positive" />
              </Link>
            ))}
          </div>
        </div>
      )}
    </>
  );
}


/* ── 시장 신호 대시보드 ─────────────────────── */
interface MarketTrend {
  foreign_streak_days: number;
  foreign_streak_amount: number;
  inst_streak_days: number;
  inst_streak_amount: number;
}
interface MarketSignalsData {
  date: string;
  trend: {
    kospi: MarketTrend;
    kosdaq: MarketTrend;
  };
  activity: {
    high_52w: number;
    low_52w: number;
    foreign_buy_breadth: number;
    foreign_sell_breadth: number;
    inst_buy_breadth: number;
    inst_sell_breadth: number;
  };
  signals: {
    buy_reversal: number;
    sell_reversal: number;
    accumulation: number;
    divergence: number;
  };
  verdict: string;
}

function MarketSignals() {
  const [data, setData] = useState<MarketSignalsData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/data/market-signals.json")
      .then((r) => r.json())
      .then((d) => setData(d))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, []);

  if (loading || !data) {
    return (
      <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-4 sm:p-6">
        <div className="h-6 w-40 bg-white/[0.04] rounded animate-pulse mb-4" />
        <div className="space-y-3">
          <div className="h-12 bg-white/[0.04] rounded animate-pulse" />
          <div className="h-12 bg-white/[0.04] rounded animate-pulse" />
          <div className="h-20 bg-white/[0.04] rounded animate-pulse" />
        </div>
      </div>
    );
  }

  const { trend } = data;

  // 금액 포매팅 (입력: 백만원)
  const fmtAmount = (mw: number) => {
    const won = mw * 1_000_000;
    const abs = Math.abs(won);
    const sign = won > 0 ? "+" : won < 0 ? "-" : "";
    if (abs >= 1e12) return `${sign}${(abs / 1e12).toFixed(1)}조원`;
    if (abs >= 1e8) return `${sign}${Math.round(abs / 1e8).toLocaleString()}억원`;
    return `${sign}${Math.round(abs).toLocaleString()}원`;
  };

  const renderStreak = (label: string, days: number, amount: number) => {
    const direction = days > 0 ? "매수" : days < 0 ? "매도" : "관망";
    const color = days > 0 ? "text-[#f85149]" : days < 0 ? "text-[#58a6ff]" : "text-[var(--text-muted)]";
    const prefix = days !== 0 ? "연속 " : "";
    return (
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[12px] text-white font-medium w-12 shrink-0">{label}</span>
        <span className={`text-[12px] sm:text-[13px] font-semibold ${color}`}>
          {prefix}{direction} <span className="num">{Math.abs(days)}</span>일
        </span>
        <span className={`text-[10px] sm:text-[11px] num ml-auto ${color}`}>{fmtAmount(amount)}</span>
      </div>
    );
  };

  return (
    <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-4 sm:p-5">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="bg-blue-500/[0.04] border border-blue-500/[0.1] rounded-xl p-3">
          <div className="text-[11px] font-semibold text-blue-400 mb-2.5">KOSPI</div>
          <div className="space-y-2">
            {renderStreak("외국인", trend.kospi.foreign_streak_days, trend.kospi.foreign_streak_amount)}
            {renderStreak("기관", trend.kospi.inst_streak_days, trend.kospi.inst_streak_amount)}
          </div>
        </div>
        <div className="bg-purple-500/[0.04] border border-purple-500/[0.1] rounded-xl p-3">
          <div className="text-[11px] font-semibold text-purple-400 mb-2.5">KOSDAQ</div>
          <div className="space-y-2">
            {renderStreak("외국인", trend.kosdaq.foreign_streak_days, trend.kosdaq.foreign_streak_amount)}
            {renderStreak("기관", trend.kosdaq.inst_streak_days, trend.kosdaq.inst_streak_amount)}
          </div>
        </div>
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
      <h3 className="text-[13px] sm:text-[14px] font-semibold text-white">{title}</h3>
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
            <div className="text-right shrink-0 text-[12px] sm:text-[13px]">
              <CNum v={s.combined["1m"]} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── 섹션 헤더 ────────────────────────────────── */
function SectionHeader({ title, desc }: { title: string; desc?: string }) {
  return (
    <div className="mb-4">
      <h2 className="text-[18px] sm:text-[20px] font-semibold text-white tracking-tight leading-tight">{title}</h2>
      {desc && <p className="text-[12px] text-[var(--text-muted)] mt-1.5">{desc}</p>}
      <div className="h-px bg-white/[0.1] mt-3" />
    </div>
  );
}

/* ── 메인 ─────────────────────────────────────── */
export default function Dashboard() {
  const [market, setMarket] = useState<Record<string, MarketData> | null>(null);
  const [stocks, setStocks] = useState<StockRanking[]>([]);
  const [meta, setMeta] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [latestReport, setLatestReport] = useState<{ date: string; title: string; body: string } | null>(null);

  useEffect(() => {
    Promise.all([
      fetch("/data/market-overview.json").then((r) => r.json()),
      fetch("/data/stock-rankings.json").then((r) => r.json()),
      fetch("/data/meta.json").then((r) => r.json()),
      fetch("/data/reports/index.json").then((r) => r.json()).catch(() => []),
    ])
      .then(([m, s, mt, idx]) => {
        setMarket(m.data); setStocks(s.data); setMeta(mt);
        if (idx.length > 0) {
          fetch(`/data/reports/${idx[0].date}.json`)
            .then((r) => r.json())
            .then((r) => setLatestReport(r))
            .catch(() => {});
        }
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="space-y-8">
        {/* Intro 스켈레톤 */}
        <div className="space-y-2">
          <div className="h-3 w-80 max-w-full bg-white/[0.04] rounded animate-pulse" />
          <div className="h-3 w-48 bg-white/[0.04] rounded animate-pulse" />
        </div>
        {/* 섹션 1: HERO + 지수 */}
        <div className="space-y-3">
          <div className="h-6 w-32 bg-white/[0.04] rounded animate-pulse" />
          <div className="h-px bg-white/[0.06]" />
          <div className="h-40 bg-white/[0.04] rounded-2xl animate-pulse" />
          <div className="flex gap-4">
            <div className="h-32 flex-1 bg-white/[0.04] rounded-2xl animate-pulse" />
            <div className="h-32 flex-1 bg-white/[0.04] rounded-2xl animate-pulse" />
          </div>
        </div>
        {/* 섹션 2: 시장 수급 */}
        <div className="space-y-3">
          <div className="h-6 w-40 bg-white/[0.04] rounded animate-pulse" />
          <div className="h-px bg-white/[0.06]" />
          <div className="h-28 bg-white/[0.04] rounded-2xl animate-pulse" />
        </div>
        {/* 섹션 3: 오늘의 주목 + TOP10 */}
        <div className="space-y-3">
          <div className="h-6 w-32 bg-white/[0.04] rounded animate-pulse" />
          <div className="h-px bg-white/[0.06]" />
          <div className="h-60 bg-white/[0.04] rounded-2xl animate-pulse" />
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Intro */}
      <div>
        <p className="text-[13px] sm:text-[14px] text-[var(--text-secondary)]">외국인·기관이 어디에 돈을 넣고 있는지, 어떤 종목이 주도하는지 한눈에</p>
        {meta && (
          <p className="text-[11px] text-[var(--text-muted)] mt-1">
            기준일 {meta.business_date} {(() => {
            const t = meta.last_updated;
            if (t.includes("시")) return t;
            try {
              const d = new Date(t);
              if (isNaN(d.getTime())) return "";
              d.setHours(d.getHours() + 9);
              const h = d.getHours();
              const ampm = h < 12 ? "오전" : "오후";
              const h12 = h <= 12 ? h : h - 12;
              return `${ampm} ${h12 || 12}시 ${String(d.getMinutes()).padStart(2, "0")}분`;
            } catch { return ""; }
          })()} 업데이트
          </p>
        )}
      </div>

      {/* Section 1: 오늘의 시장 */}
      <section>
        <SectionHeader title="오늘의 시장" desc="AI 시황과 주요 지수" />
        <div className="space-y-4">
          {latestReport && (
            <Link href={`/reports/${latestReport.date}`}
              className="block bg-gradient-to-br from-[var(--bg-card)] to-[#161b22] border border-white/[0.08] rounded-2xl p-5 sm:p-7 hover:border-white/[0.18] transition group"
            >
              <div className="flex items-center gap-2 mb-3">
                <span className="text-[10px] px-1.5 py-0.5 rounded-md bg-[var(--accent-blue)]/20 text-[var(--accent-blue)] font-medium">AI 시황</span>
                <span className="text-[10px] text-[var(--text-muted)] num">{latestReport.date}</span>
              </div>
              <h3 className="text-[17px] sm:text-[21px] font-semibold text-white leading-snug mb-2.5 tracking-tight">
                {latestReport.title}
              </h3>
              {latestReport.body && (
                <p className="text-[12px] sm:text-[13px] text-[var(--text-secondary)] leading-relaxed line-clamp-2">
                  {latestReport.body}
                </p>
              )}
              <div className="flex items-center gap-1 mt-4 text-[12px] text-[var(--accent-blue)] group-hover:gap-2 transition-all">
                <span>자세히 보기</span>
                <svg width="11" height="11" viewBox="0 0 16 16" fill="currentColor"><path d="M6.22 3.22a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06l-4.25 4.25a.751.751 0 0 1-1.042-.018.751.751 0 0 1-.018-1.042L9.94 8 6.22 4.28a.75.75 0 0 1 0-1.06Z"/></svg>
              </div>
            </Link>
          )}
          <div className="flex flex-col sm:flex-row gap-4">
            <IndexCard name="KOSPI" data={market?.KOSPI ?? null} />
            <IndexCard name="KOSDAQ" data={market?.KOSDAQ ?? null} />
          </div>
        </div>
      </section>

      {/* Section 3: 수급 추세 (축소) */}
      <section>
        <SectionHeader title="수급 추세" desc="외국인·기관 연속 매수·매도" />
        <MarketSignals />
      </section>

      {/* Section 4: 오늘의 주목 */}
      <section>
        <SectionHeader title="오늘의 주목" desc="주도 섹터·종목 분석" />
        <div className="space-y-4">
          <TodayHighlight stocks={stocks} />
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <TopTable title="1개월 순매수 TOP 10" desc="외국인+기관 합산 순매수 금액 기준" stocks={stocks} type="buy" />
            <TopTable title="1개월 순매도 TOP 10" desc="외국인+기관 합산 순매도 금액 기준" stocks={stocks} type="sell" />
          </div>
        </div>
      </section>

      {/* CTA */}
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
