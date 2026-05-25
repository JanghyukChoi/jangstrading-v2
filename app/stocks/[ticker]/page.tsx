"use client";

import { useEffect, useState, use } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, Cell,
  LineChart, Line, CartesianGrid,
} from "recharts";

export const dynamic = "force-static";
export const dynamicParams = true;

/* ── 타입 ─────────────────────────────────────── */
interface AvgCostData {
  price: number;
  foreign?: { avg_cost: number; pnl_pct: number };
  institution?: { avg_cost: number; pnl_pct: number };
}

interface StockData {
  name: string;
  market: string;
  ticker: string;
  per?: number | null;
  pbr?: number | null;
  eps?: number | null;
  bps?: number | null;
  div_yield?: number | null;
  market_cap?: number | null;
  price_change?: Record<string, number>;
  avg_cost?: AvgCostData | null;
  sector?: string;
  sector_mid?: string;
  inst_detail?: Record<string, any>;
  foreign: Record<string, number>;
  institution: Record<string, number>;
  combined: Record<string, number>;
}

/* ── 유틸 ─────────────────────────────────────── */
function fmt(n: number) {
  return n.toLocaleString("ko-KR", { maximumFractionDigits: 1 });
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
function fmtCap(n: number) {
  if (n >= 10000) return `${(n / 10000).toFixed(1)}조`;
  return `${n.toLocaleString()}억`;
}
function CNum({ v, size = "text-sm" }: { v: number; size?: string }) {
  const cls = v > 0 ? "positive" : v < 0 ? "negative" : "text-[var(--text-secondary)]";
  const str = fmtUnit(v);
  const m = str.match(/^(.+?)([가-힣]+)$/);
  return m ? (
    <span className={`${cls} ${size}`}><span className="num">{m[1]}</span>{m[2]}</span>
  ) : (
    <span className={`num ${cls} ${size}`}>{str}</span>
  );
}
// 한글 단위 분리 헬퍼
function NumUnit({ v, cls = "" }: { v: number; cls?: string }) {
  const str = fmtUnit(v);
  const m = str.match(/^(.+?)([가-힣]+)$/);
  return m ? (
    <span className={cls}><span className="num">{m[1]}</span>{m[2]}</span>
  ) : (
    <span className={`num ${cls}`}>{str}</span>
  );
}

/* ── 지표 카드 ────────────────────────────────── */
function MetricCard({ label, value, unit }: { label: string; value: string | null; unit?: string }) {
  const m = value?.match(/^(.+?)([가-힣]+)$/);
  return (
    <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-xl p-3 sm:p-4 text-center">
      <div className="text-[10px] sm:text-[11px] text-[var(--text-muted)] mb-1.5">{label}</div>
      <div className="text-sm sm:text-lg font-semibold text-white truncate">
        {value == null ? (
          <span className="text-[var(--text-muted)]">-</span>
        ) : m ? (
          <><span className="num">{m[1]}</span>{m[2]}</>
        ) : (
          <span className="num">{value}</span>
        )}
      </div>
      {unit && value && <div className="text-[9px] sm:text-[10px] text-[var(--text-muted)] mt-0.5">{unit}</div>}
    </div>
  );
}

/* ── 수급 바 차트 ─────────────────────────────── */
function SupplyChart({ title, data }: { title: string; data: Record<string, number> }) {
  const periods = ["1d", "1w", "1m", "3m", "6m"];
  const labels: Record<string, string> = { "1d": "1일", "1w": "1주", "1m": "1개월", "3m": "3개월", "6m": "6개월" };
  const chartData = periods.map((p) => ({ period: labels[p], value: Math.round(data[p]) }));

  const customTooltip = ({ active, payload, label }: any) => {
    if (!active || !payload?.[0]) return null;
    const v = payload[0].value;
    return (
      <div className="bg-[#1c2128] border border-white/10 rounded-xl px-3 py-2 text-[11px] shadow-xl">
        <div className="text-[var(--text-secondary)] mb-1">{label}</div>
        <div className={`font-medium ${v > 0 ? "text-[#f85149]" : "text-[#58a6ff]"}`}>
          <NumUnit v={v} />
        </div>
      </div>
    );
  };

  return (
    <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-4 sm:p-6">
      <h3 className="text-xs sm:text-sm font-medium text-[var(--text-secondary)] mb-4">{title}</h3>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={chartData} margin={{ top: 5, right: 5, bottom: 0, left: -20 }}>
          <XAxis dataKey="period" tick={{ fill: "#484f58", fontSize: 10 }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fill: "#484f58", fontSize: 9 }} axisLine={false} tickLine={false}
            tickFormatter={(v) => {
              const won = v * 1_000_000;
              const abs = Math.abs(won);
              if (abs >= 1_000_000_000_000) return `${(won / 1_000_000_000_000).toFixed(0)}조`;
              if (abs >= 100_000_000) return `${Math.round(won / 100_000_000)}억`;
              if (abs >= 10_000) return `${Math.round(won / 10_000)}만`;
              if (abs === 0) return "0";
              return `${Math.round(won)}`;
            }}
          />
          <Tooltip content={customTooltip} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
          <ReferenceLine y={0} stroke="rgba(255,255,255,0.08)" />
          <Bar dataKey="value" radius={[4, 4, 0, 0]} maxBarSize={36}>
            {chartData.map((entry, i) => (
              <Cell key={i} fill={entry.value >= 0 ? "#f85149" : "#58a6ff"} fillOpacity={0.85} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/* ── 누적 순매수 라인 차트 ─────────────────── */
interface TimeseriesData {
  ticker: string;
  dates: string[];
  foreign: number[];
  inst: number[];
  pension: number[];
  prices: number[];
}
type FlowPeriod = "1m" | "3m" | "6m" | "1y";

function CumulativeFlowChart({ ticker }: { ticker: string }) {
  const [data, setData] = useState<TimeseriesData | null>(null);
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState<FlowPeriod>("3m");

  useEffect(() => {
    setLoading(true);
    fetch(`/data/timeseries/${ticker}.json`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => setData(d))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [ticker]);

  if (loading) {
    return (
      <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-4 sm:p-6">
        <div className="h-6 w-40 bg-white/[0.04] rounded animate-pulse mb-3" />
        <div className="h-60 bg-white/[0.04] rounded animate-pulse" />
      </div>
    );
  }
  if (!data || data.dates.length < 5) return null;

  const dayMap: Record<FlowPeriod, number> = { "1m": 20, "3m": 60, "6m": 120, "1y": 252 };
  const startIdx = Math.max(0, data.dates.length - dayMap[period]);
  const sd = data.dates.slice(startIdx);
  const sf = data.foreign.slice(startIdx);
  const si = data.inst.slice(startIdx);

  let cumF = 0;
  let cumI = 0;
  const chartData = sd.map((date, idx) => {
    cumF += sf[idx];
    cumI += si[idx];
    return {
      idx, // 균등 간격 보장용 (X축 numeric)
      date, // 풀 날짜 — tooltip·tick 표시용
      foreign: Math.round(cumF * 1_000_000),
      inst: Math.round(cumI * 1_000_000),
    };
  });

  const formatY = (v: number) => {
    const abs = Math.abs(v);
    const sign = v > 0 ? "+" : v < 0 ? "-" : "";
    if (abs >= 1e12) return `${sign}${(abs / 1e12).toFixed(1)}조`;
    if (abs >= 1e8) return `${sign}${Math.round(abs / 1e8).toLocaleString()}억`;
    if (abs >= 1e4) return `${sign}${Math.round(abs / 1e4).toLocaleString()}만`;
    return `${sign}${Math.round(abs)}`;
  };

  const CustomTooltip = ({ active, payload }: any) => {
    if (!active || !payload || payload.length === 0) return null;
    const f = payload.find((p: any) => p.dataKey === "foreign")?.value;
    const i = payload.find((p: any) => p.dataKey === "inst")?.value;
    // X축이 numeric(idx)이라 label 대신 payload[0].payload.date 사용
    const dateStr = payload[0]?.payload?.date as string | undefined;
    const displayDate = dateStr && dateStr.length >= 10
      ? `${dateStr.slice(0, 4)}.${dateStr.slice(5, 7)}.${dateStr.slice(8, 10)}`
      : dateStr;
    return (
      <div className="bg-[#1c2128] border border-white/10 rounded-xl px-3 py-2 text-[11px] shadow-xl space-y-0.5">
        <div className="text-white mb-1">{displayDate}</div>
        {f != null && (
          <div className="flex justify-between gap-4">
            <span className="text-[#d29922]">외국인</span>
            <span className={`num ${f >= 0 ? "text-[#f85149]" : "text-[#58a6ff]"}`}>{formatY(f)}원</span>
          </div>
        )}
        {i != null && (
          <div className="flex justify-between gap-4">
            <span className="text-[#06b6d4]">기관</span>
            <span className={`num ${i >= 0 ? "text-[#f85149]" : "text-[#58a6ff]"}`}>{formatY(i)}원</span>
          </div>
        )}
      </div>
    );
  };

  const periodOptions: { key: FlowPeriod; label: string }[] = [
    { key: "1m", label: "1개월" },
    { key: "3m", label: "3개월" },
    { key: "6m", label: "6개월" },
    { key: "1y", label: "1년" },
  ];

  return (
    <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-4 sm:p-6">
      <div className="flex items-baseline justify-between gap-2 mb-4 flex-wrap">
        <div>
          <h3 className="text-xs sm:text-sm font-medium text-[var(--text-secondary)]">외국인·기관 누적 순매수</h3>
          <p className="text-[10px] text-[var(--text-muted)] mt-0.5">
            기간 시작점 = 0, 일별 순매수 누적
          </p>
        </div>
        <div className="flex rounded-xl overflow-hidden border border-white/[0.06] bg-[var(--bg-card)]">
          {periodOptions.map((p) => (
            <button
              key={p.key}
              onClick={() => setPeriod(p.key)}
              className={`px-2.5 py-1 text-[11px] transition ${
                period === p.key
                  ? "bg-[var(--accent-blue)] text-white font-medium"
                  : "text-[var(--text-secondary)] hover:text-white"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={chartData} margin={{ top: 10, right: 10, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" vertical={false} />
          <XAxis
            dataKey="idx"
            type="number"
            domain={[0, chartData.length - 1]}
            tick={{ fill: "#484f58", fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            interval="preserveStartEnd"
            minTickGap={40}
            tickFormatter={(idx: number) => {
              const d = chartData[idx]?.date;
              return d && typeof d === "string" && d.length >= 10 ? d.slice(5) : "";
            }}
          />
          <YAxis
            tick={{ fill: "#484f58", fontSize: 9 }}
            axisLine={false}
            tickLine={false}
            tickFormatter={formatY}
            width={50}
          />
          <ReferenceLine y={0} stroke="rgba(255,255,255,0.12)" />
          <Tooltip content={<CustomTooltip />} cursor={{ stroke: "rgba(255,255,255,0.1)", strokeWidth: 1 }} />
          <Line type="monotone" dataKey="foreign" stroke="#d29922" strokeWidth={2} dot={{ r: 1.2, fill: "#d29922", stroke: "none" }} activeDot={{ r: 4 }} name="외국인" isAnimationActive={false} />
          <Line type="monotone" dataKey="inst" stroke="#06b6d4" strokeWidth={2} dot={{ r: 1.2, fill: "#06b6d4", stroke: "none" }} activeDot={{ r: 4 }} name="기관" isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>

      <div className="flex items-center justify-center gap-4 mt-2 text-[10px] text-[var(--text-secondary)]">
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-0.5 bg-[#d29922]" />외국인
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-0.5 bg-[#06b6d4]" />기관
        </span>
      </div>
      <p className="text-[10px] text-[var(--text-muted)] text-center mt-2">
        라인 위로 = 누적 매수 · 아래로 = 누적 매도 (색상은 투자자 구분)
      </p>
    </div>
  );
}

/* ── 메인 ─────────────────────────────────────── */
export default function StockDetailPage({ params }: { params: Promise<{ ticker: string }> }) {
  const { ticker } = use(params);
  const router = useRouter();
  const [stockData, setStockData] = useState<StockData | null>(null);
  const [stockThemes, setStockThemes] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [instPeriod, setInstPeriod] = useState<"1d"|"1w"|"1m"|"3m"|"6m">("1m");

  useEffect(() => {
    Promise.all([
      fetch("/data/stock-rankings.json").then((r) => r.json()),
      fetch("/data/theme-map.json").then((r) => r.json()).catch(() => ({})),
    ])
      .then(([d, themeMap]) => {
        const found = d.data.find((s: StockData) => s.ticker === ticker);
        setStockData(found || null);
        if (found) document.title = `${found.name}(${ticker}) 외국인 기관 수급 분석 | JangsTrading`;
        // 이 종목이 속한 테마 찾기
        const themes: string[] = [];
        for (const [name, tickers] of Object.entries(themeMap as Record<string, string[]>)) {
          if (tickers.includes(ticker)) themes.push(name);
        }
        setStockThemes(themes);
      })
      .finally(() => setLoading(false));
  }, [ticker]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-5 h-5 border-2 border-[var(--accent-blue)] border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!stockData) {
    return (
      <div className="text-center py-20 text-[var(--text-muted)]">
        종목을 찾을 수 없습니다.
        <div className="mt-4">
          <button onClick={() => router.back()} className="text-[var(--accent-blue)] hover:underline text-sm">← 뒤로가기</button>
        </div>
      </div>
    );
  }

  const periods = ["1d", "1w", "1m", "3m", "6m"] as const;
  const periodLabels: Record<string, string> = { "1d": "1일", "1w": "1주", "1m": "1개월", "3m": "3개월", "6m": "6개월" };
  const tvUrl = `https://www.tradingview.com/chart/?symbol=KRX%3A${stockData.ticker}`;

  return (
    <div className="space-y-4">
      {/* 헤더 (3단 구조) */}
      <div className="space-y-3 pb-4 border-b border-white/[0.08]">
        {/* 상단: 뒤로가기 + 차트 버튼 */}
        <div className="flex items-center justify-between gap-2">
          <button onClick={() => router.back()} className="text-[var(--text-muted)] hover:text-white transition text-sm">← 목록</button>
          <a href={tvUrl} target="_blank" rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-[#2962FF] text-white rounded-lg text-xs font-medium hover:brightness-110 transition">
            <svg width="12" height="12" viewBox="0 0 36 28" fill="currentColor">
              <path d="M14 22H7V6h7V0H0v28h21v-7h-7v1zm22-22h-7v7h-8v7h8v7h7V0z"/>
            </svg>
            차트
          </a>
        </div>

        {/* 중단: 종목명 + 시장 + 티커 */}
        <div className="flex items-center gap-2 flex-wrap">
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight">{stockData.name}</h1>
          <span className={`text-[10px] px-2 py-0.5 rounded-lg font-medium ${
            stockData.market === "KOSPI" ? "bg-blue-500/10 text-blue-400" : "bg-purple-500/10 text-purple-400"
          }`}>{stockData.market}</span>
          <span className="text-[var(--text-muted)] text-xs num">{stockData.ticker}</span>
        </div>

        {/* 하단: 큰 현재가 + 전일대비 */}
        {stockData.avg_cost?.price != null && (
          <div className="flex items-baseline gap-3 flex-wrap">
            <span className="text-[32px] sm:text-[42px] font-bold text-white tracking-tight leading-none">
              <span className="num">{stockData.avg_cost.price.toLocaleString()}</span>
              <span className="text-[18px] sm:text-[22px] font-medium text-[var(--text-secondary)] ml-1">원</span>
            </span>
            {stockData.price_change?.["1d"] != null && (
              <span className={`text-[15px] sm:text-[17px] font-semibold ${
                stockData.price_change["1d"] > 0 ? "positive" : stockData.price_change["1d"] < 0 ? "negative" : "text-[var(--text-secondary)]"
              }`}>
                {stockData.price_change["1d"] > 0 ? "▲ " : stockData.price_change["1d"] < 0 ? "▼ " : ""}
                <span className="num">{stockData.price_change["1d"] > 0 ? "+" : ""}{stockData.price_change["1d"].toFixed(2)}%</span>
              </span>
            )}
            <span className="text-[11px] text-[var(--text-muted)]">전일대비</span>
          </div>
        )}
      </div>

      {/* 업종 · 테마 */}
      {(stockData.sector || stockThemes.length > 0) && (
        <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-4 sm:p-6">
          <h3 className="text-xs sm:text-sm font-medium text-[var(--text-secondary)] mb-4">업종 · 테마 분류</h3>

          <div className="flex flex-wrap gap-2">
            {stockData.sector && stockData.sector !== "기타" && (
              <Link
                href={`/sectors/${encodeURIComponent(stockData.sector)}`}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-500/[0.08] border border-blue-500/[0.15] hover:border-blue-500/[0.3] transition text-[12px]"
              >
                <span className="text-[10px] text-blue-400/60">대분류</span>
                <span className="text-blue-400 font-medium">{stockData.sector}</span>
              </Link>
            )}
            {stockData.sector_mid && stockData.sector_mid !== "기타" && (
              <Link
                href={`/sectors/${encodeURIComponent(stockData.sector_mid)}`}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-500/[0.08] border border-purple-500/[0.15] hover:border-purple-500/[0.3] transition text-[12px]"
              >
                <span className="text-[10px] text-purple-400/60">중분류</span>
                <span className="text-purple-400 font-medium">{stockData.sector_mid}</span>
              </Link>
            )}
            {stockThemes.map((theme) => (
              <Link
                key={theme}
                href={`/sectors/${encodeURIComponent(theme)}`}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/[0.04] border border-white/[0.06] hover:border-white/[0.12] transition text-[12px]"
              >
                <span className="text-[10px] text-[var(--text-muted)]">테마</span>
                <span className="text-[var(--text-secondary)] font-medium">{theme}</span>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* 재무 지표 — 모바일 3열, 데스크톱 6열 */}
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-2 sm:gap-3">
        <MetricCard label="시가총액" value={stockData.market_cap != null ? fmtCap(stockData.market_cap) : null} />
        <MetricCard label="PER" value={stockData.per != null ? stockData.per.toFixed(1) : null} unit="배" />
        <MetricCard label="PBR" value={stockData.pbr != null ? stockData.pbr.toFixed(2) : null} unit="배" />
        <MetricCard label="EPS" value={stockData.eps != null ? stockData.eps.toLocaleString() : null} unit="원" />
        <MetricCard label="BPS" value={stockData.bps != null ? stockData.bps.toLocaleString() : null} unit="원" />
        <MetricCard label="배당수익률" value={stockData.div_yield != null ? stockData.div_yield.toFixed(2) : null} unit="%" />
      </div>

      {/* 추정 평균단가 */}
      {stockData.avg_cost && (stockData.avg_cost.foreign || stockData.avg_cost.institution) && (
        <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-4 sm:p-6">
          <h3 className="text-xs sm:text-sm font-medium text-[var(--text-secondary)] mb-1">추정 평균단가</h3>
          <p className="text-[10px] text-[var(--text-muted)] mb-4">최근 6개월 이동평균 원가법 기준 · 현재가 {stockData.avg_cost.price.toLocaleString()}원</p>

          <div className="flex flex-col sm:flex-row gap-3">
            {([
              { key: "foreign" as const, label: "외국인", color: "#f85149" },
              { key: "institution" as const, label: "기관", color: "#58a6ff" },
            ]).map(({ key, label, color }) => {
              const d = stockData.avg_cost?.[key];
              if (!d) return null;
              const isProfit = d.pnl_pct >= 0;
              return (
                <div key={key} className="flex-1 rounded-xl bg-white/[0.02] border border-white/[0.04] p-4">
                  <div className="flex items-center gap-2 mb-3">
                    <span className="w-2 h-2 rounded-full" style={{ background: color }} />
                    <span className="text-[13px] text-[var(--text-secondary)]">{label}</span>
                  </div>

                  <div className="flex items-end justify-between mb-3">
                    <div>
                      <div className="text-[10px] text-[var(--text-muted)] mb-1">추정 평균단가</div>
                      <div className="text-lg sm:text-xl font-semibold text-white"><span className="num">{d.avg_cost.toLocaleString()}</span>원</div>
                    </div>
                    <div className={`text-right px-3 py-1.5 rounded-lg ${
                      isProfit ? "bg-red-500/[0.08]" : "bg-blue-500/[0.08]"
                    }`}>
                      <div className={`text-lg font-bold num ${isProfit ? "positive" : "negative"}`}>
                        {isProfit ? "+" : ""}{d.pnl_pct}%
                      </div>
                      <div className="text-[10px] text-[var(--text-muted)]">
                        {isProfit ? "수익 중" : "손실 중"}
                      </div>
                    </div>
                  </div>

                  {/* 현재가 대비 바 */}
                  {(() => {
                    const price = stockData.avg_cost!.price;
                    const minP = Math.min(d.avg_cost, price) * 0.95;
                    const maxP = Math.max(d.avg_cost, price) * 1.05;
                    const range = maxP - minP;
                    const costPos = ((d.avg_cost - minP) / range) * 100;
                    const pricePos = ((price - minP) / range) * 100;
                    return (
                      <div className="relative h-6 mt-1">
                        <div className="absolute top-2.5 left-0 right-0 h-1 rounded-full bg-white/[0.06]" />
                        {/* 평균단가 마커 */}
                        <div className="absolute top-0" style={{ left: `${costPos}%`, transform: "translateX(-50%)" }}>
                          <div className="w-2.5 h-2.5 rounded-full border-2" style={{ borderColor: color, background: "#0d1117" }} />
                          <div className="text-[8px] text-[var(--text-muted)] mt-0.5 whitespace-nowrap" style={{ transform: "translateX(-30%)" }}>매수가</div>
                        </div>
                        {/* 현재가 마커 */}
                        <div className="absolute top-0" style={{ left: `${pricePos}%`, transform: "translateX(-50%)" }}>
                          <div className="w-2.5 h-2.5 rounded-full bg-white" />
                          <div className="text-[8px] text-[var(--text-muted)] mt-0.5 whitespace-nowrap" style={{ transform: "translateX(-30%)" }}>현재가</div>
                        </div>
                        {/* 영역 */}
                        <div className="absolute top-2.5 h-1 rounded-full" style={{
                          left: `${Math.min(costPos, pricePos)}%`,
                          width: `${Math.abs(pricePos - costPos)}%`,
                          background: isProfit ? "rgba(248,81,73,0.4)" : "rgba(88,166,255,0.4)",
                        }} />
                      </div>
                    );
                  })()}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 외국인·기관 누적 순매수 라인 차트 */}
      <CumulativeFlowChart ticker={stockData.ticker} />

      {/* 기관 세부 */}
      {stockData.inst_detail && Object.keys(stockData.inst_detail).length > 0 && (() => {
        const instPeriodData = stockData.inst_detail![instPeriod] ?? stockData.inst_detail!;
        // 기간별 데이터인지 플랫 데이터인지 체크
        const isNested = typeof Object.values(stockData.inst_detail!)[0] === "object";
        const detail: Record<string, number> = isNested ? instPeriodData : stockData.inst_detail!;
        if (!detail || typeof detail !== "object") return null;
        const entries = Object.entries(detail)
          .filter(([, v]) => typeof v === "number")
          .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
        if (entries.length === 0) return null;
        const maxVal = Math.max(...entries.map(([, v]) => Math.abs(v)), 1);
        const total = entries.reduce((sum, [, v]) => sum + v, 0);

        return (
          <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-4 sm:p-6">
            <h3 className="text-xs sm:text-sm font-medium text-[var(--text-secondary)] mb-1">기관 세부 주체별 순매수</h3>
            <p className="text-[10px] text-[var(--text-muted)] mb-3">기관 합계 {fmtUnit(total)}</p>
            {isNested && (
              <div className="flex rounded-xl overflow-hidden border border-white/[0.06] bg-[var(--bg-card)] mb-4 w-fit">
                {(["1d","1w","1m","3m","6m"] as const).map((p) => (
                  <button key={p} onClick={() => setInstPeriod(p)}
                    className={`px-3 py-[6px] text-[11px] transition-all ${instPeriod === p ? "bg-[var(--accent-blue)] text-white font-medium" : "text-[var(--text-secondary)] hover:text-white hover:bg-white/[0.04]"}`}>
                    {periodLabels[p]}
                  </button>
                ))}
              </div>
            )}
            <div className="space-y-2.5">
              {entries.map(([name, value]) => {
                const pct = maxVal > 0 ? Math.abs(value) / maxVal * 100 : 0;
                const isPos = value > 0;
                return (
                  <div key={name} className="flex items-center gap-3">
                    <span className="text-[12px] sm:text-[13px] text-[var(--text-secondary)] w-16 sm:w-20 shrink-0">{name}</span>
                    <div className="flex-1 h-4 rounded-full bg-white/[0.04] overflow-hidden">
                      <div
                        className={`h-full rounded-full ${isPos ? "bg-gradient-to-r from-red-500/60 to-red-500/20" : "bg-gradient-to-r from-blue-400/60 to-blue-400/20"}`}
                        style={{ width: `${Math.max(pct, 2)}%` }}
                      />
                    </div>
                    <NumUnit v={value} cls={`text-[12px] sm:text-[13px] font-medium w-24 text-right shrink-0 ${isPos ? "positive" : value < 0 ? "negative" : ""}`} />
                  </div>
                );
              })}
            </div>
          </div>
        );
      })()}

      {/* 상세 테이블 */}
      <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-4 sm:p-6">
        <h3 className="text-xs sm:text-sm font-medium text-[var(--text-secondary)] mb-1">기간별 수급 vs 주가</h3>
        <p className="text-[10px] text-[var(--text-muted)] mb-3">같은 기간 수급 금액과 주가 변동률을 비교하여 수급 대비 주가 반응을 확인</p>
        <table className="w-full text-[12px] sm:text-[13px]">
          <thead>
            <tr className="text-[var(--text-muted)] text-[10px] sm:text-[11px] border-b border-white/[0.06]">
              <th className="text-left py-2 font-normal">기간</th>
              <th className="text-right py-2 font-normal">외국인</th>
              <th className="text-right py-2 font-normal">기관</th>
              <th className="text-right py-2 font-normal">합계</th>
              <th className="text-right py-2 font-normal">주가 변동</th>
            </tr>
          </thead>
          <tbody>
            {periods.map((p) => {
              const pc = stockData.price_change?.[p];
              const combined = stockData.combined[p];
              // 수급은 매수인데 주가가 하락 = 괴리 (하이라이트)
              const isDivergence = combined > 0 && pc != null && pc < -3;
              return (
                <tr key={p} className={`border-t border-white/[0.03] ${isDivergence ? "bg-amber-500/[0.04]" : ""}`}>
                  <td className="py-2.5 text-[var(--text-secondary)]">{periodLabels[p]}</td>
                  <td className="py-2.5 text-right"><CNum v={stockData.foreign[p]}/></td>
                  <td className="py-2.5 text-right"><CNum v={stockData.institution[p]}/></td>
                  <td className="py-2.5 text-right font-medium"><CNum v={combined}/></td>
                  <td className="py-2.5 text-right">
                    {pc != null ? (
                      <span className={`num ${pc > 0 ? "positive" : pc < 0 ? "negative" : "text-[var(--text-secondary)]"}`}>
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

    </div>
  );
}
