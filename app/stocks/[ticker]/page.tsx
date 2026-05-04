"use client";

import { useEffect, useState, use } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, Cell,
} from "recharts";

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
  return <span className={`num ${cls} ${size}`}>{fmtUnit(v)}</span>;
}

/* ── 지표 카드 ────────────────────────────────── */
function MetricCard({ label, value, unit }: { label: string; value: string | null; unit?: string }) {
  return (
    <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-xl p-3 sm:p-4 text-center">
      <div className="text-[10px] sm:text-[11px] text-[var(--text-muted)] mb-1.5">{label}</div>
      <div className="text-sm sm:text-lg font-semibold num text-white truncate">
        {value ?? <span className="text-[var(--text-muted)]">-</span>}
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
        <div className={`num font-medium ${v > 0 ? "text-[#f85149]" : "text-[#58a6ff]"}`}>
          {fmtUnit(v)}
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

/* ── 메인 ─────────────────────────────────────── */
export default function StockDetailPage({ params }: { params: Promise<{ ticker: string }> }) {
  const { ticker } = use(params);
  const router = useRouter();
  const [stockData, setStockData] = useState<StockData | null>(null);
  const [stockThemes, setStockThemes] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch("/data/stock-rankings.json").then((r) => r.json()),
      fetch("/data/theme-map.json").then((r) => r.json()).catch(() => ({})),
    ])
      .then(([d, themeMap]) => {
        const found = d.data.find((s: StockData) => s.ticker === ticker);
        setStockData(found || null);
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
      {/* 헤더 */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="flex items-center gap-2 flex-wrap">
          <button onClick={() => router.back()} className="text-[var(--text-muted)] hover:text-white transition text-sm">← 목록</button>
          <div className="w-px h-4 bg-white/10" />
          <h1 className="text-xl sm:text-2xl font-bold">{stockData.name}</h1>
          <span className={`text-[10px] px-2 py-0.5 rounded-lg font-medium ${
            stockData.market === "KOSPI" ? "bg-blue-500/10 text-blue-400" : "bg-purple-500/10 text-purple-400"
          }`}>{stockData.market}</span>
          <span className="text-[var(--text-muted)] text-xs num">{stockData.ticker}</span>
        </div>
        <a href={tvUrl} target="_blank" rel="noopener noreferrer"
          className="inline-flex items-center gap-2 px-4 py-2 bg-[#2962FF] text-white rounded-xl text-xs sm:text-sm font-medium hover:brightness-110 transition self-start">
          <svg width="14" height="14" viewBox="0 0 36 28" fill="currentColor">
            <path d="M14 22H7V6h7V0H0v28h21v-7h-7v1zm22-22h-7v7h-8v7h8v7h7V0z"/>
          </svg>
          TradingView 차트
        </a>
      </div>

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
                      <div className="text-lg sm:text-xl font-semibold num text-white">{d.avg_cost.toLocaleString()}원</div>
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

      {/* 합산 요약 — 모바일: 리스트, 데스크톱: 5열 */}
      <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-4 sm:p-6">
        <h3 className="text-xs sm:text-sm font-medium text-[var(--text-secondary)] mb-4">외국인 + 기관 합산</h3>
        {/* 데스크톱: 5열 그리드 */}
        <div className="hidden sm:grid grid-cols-5 gap-4">
          {periods.map((p) => {
            const v = stockData.combined[p];
            return (
              <div key={p} className={`text-center p-4 rounded-xl ${
                v > 0 ? "bg-red-500/[0.06]" : v < 0 ? "bg-blue-500/[0.06]" : "bg-white/[0.02]"
              }`}>
                <div className="text-[11px] text-[var(--text-muted)] mb-2">{periodLabels[p]}</div>
                <CNum v={v} size="text-lg" />
              </div>
            );
          })}
        </div>
        {/* 모바일: 리스트 */}
        <div className="sm:hidden space-y-2">
          {periods.map((p) => {
            const v = stockData.combined[p];
            return (
              <div key={p} className={`flex items-center justify-between p-3 rounded-xl ${
                v > 0 ? "bg-red-500/[0.06]" : v < 0 ? "bg-blue-500/[0.06]" : "bg-white/[0.02]"
              }`}>
                <span className="text-sm text-[var(--text-secondary)]">{periodLabels[p]}</span>
                <CNum v={v} size="text-base"/>
              </div>
            );
          })}
        </div>
      </div>

      {/* 수급 차트 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <SupplyChart title="외국인 순매수 추이" data={stockData.foreign} />
        <SupplyChart title="기관 순매수 추이" data={stockData.institution} />
      </div>
      <SupplyChart title="외국인 + 기관 합산 순매수" data={stockData.combined} />

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

      {/* 업종 · 테마 */}
      {(stockData.sector || stockThemes.length > 0) && (
        <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-4 sm:p-6">
          <h3 className="text-xs sm:text-sm font-medium text-[var(--text-secondary)] mb-4">업종 · 테마 분류</h3>

          <div className="flex flex-wrap gap-2">
            {/* 대분류 */}
            {stockData.sector && stockData.sector !== "기타" && (
              <Link
                href={`/sectors/${encodeURIComponent(stockData.sector)}`}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-500/[0.08] border border-blue-500/[0.15] hover:border-blue-500/[0.3] transition text-[12px]"
              >
                <span className="text-[10px] text-blue-400/60">대분류</span>
                <span className="text-blue-400 font-medium">{stockData.sector}</span>
              </Link>
            )}

            {/* 중분류 */}
            {stockData.sector_mid && stockData.sector_mid !== "기타" && (
              <Link
                href={`/sectors/${encodeURIComponent(stockData.sector_mid)}`}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-500/[0.08] border border-purple-500/[0.15] hover:border-purple-500/[0.3] transition text-[12px]"
              >
                <span className="text-[10px] text-purple-400/60">중분류</span>
                <span className="text-purple-400 font-medium">{stockData.sector_mid}</span>
              </Link>
            )}

            {/* 테마 */}
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
    </div>
  );
}
