"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

export const dynamic = "force-static";

/* ── 타입 ─────────────────────────────────────── */
interface SectorStat {
  sector: string;
  avg_20d: number;
  t_stat: number;
  hit_rate: number;
}
interface RegimeMeta {
  label: string;
  pct_of_time: number;
  annualized_return: number;
  annualized_vol: number;
  sharpe: number;
  avg_duration_days: number;
}
interface CurrentRegime {
  regime: number;
  label: string;
  meta: RegimeMeta;
}
interface HistoryEntry {
  date: string;
  regime: number;
  label: string;
}
interface RegimeData {
  date: string;
  current_regime: CurrentRegime;
  history: HistoryEntry[];
  sectors_by_regime: Record<string, SectorStat[]>;
  regime_meta: Record<string, RegimeMeta>;
  model_meta: {
    n_regimes: number;
    features: string[];
    labels: Record<string, string>;
  };
  generated_at: string;
}

/* ── 유틸 ─────────────────────────────────────── */
const REGIME_COLOR: Record<string, { bg: string; text: string; border: string; dot: string }> = {
  Bull: { bg: "bg-emerald-500/10", text: "text-emerald-400", border: "border-emerald-500/30", dot: "bg-emerald-400" },
  Quiet: { bg: "bg-blue-500/10", text: "text-blue-400", border: "border-blue-500/30", dot: "bg-blue-400" },
  Transition: { bg: "bg-amber-500/10", text: "text-amber-400", border: "border-amber-500/30", dot: "bg-amber-400" },
  Crisis: { bg: "bg-rose-500/10", text: "text-rose-400", border: "border-rose-500/30", dot: "bg-rose-400" },
};

function regimeKey(label: string): string {
  if (label.startsWith("Bull")) return "Bull";
  if (label.startsWith("Quiet")) return "Quiet";
  if (label.startsWith("Transition")) return "Transition";
  if (label.startsWith("Crisis")) return "Crisis";
  return "Quiet";
}
function regimeShort(label: string): string {
  return label.split(" ")[0];
}
function regimeKorean(label: string): string {
  const m = label.match(/\((.+?)\)/);
  return m ? m[1] : label;
}

function fmtPct(v: number, digits = 1): string {
  const sign = v > 0 ? "+" : "";
  return `${sign}${(v * 100).toFixed(digits)}%`;
}

export default function CyclePage() {
  const [data, setData] = useState<RegimeData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/data/regime.json")
      .then((r) => r.json())
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
    document.title = "시장 사이클 분석 | JangsTrading";
  }, []);

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-48 bg-white/[0.04] rounded animate-pulse" />
        <div className="h-32 bg-white/[0.04] rounded-2xl animate-pulse" />
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {Array.from({ length: 4 }).map((_, i) => <div key={i} className="h-32 bg-white/[0.04] rounded-2xl animate-pulse" />)}
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="text-center py-16 text-[var(--text-muted)]">
        시장 사이클 데이터를 불러올 수 없습니다.
      </div>
    );
  }

  const cur = data.current_regime;
  const curKey = regimeKey(cur.label);
  const curColor = REGIME_COLOR[curKey];
  const curSectors = data.sectors_by_regime[String(cur.regime)] || [];

  // 4 국면 비교
  const regimeEntries = Object.entries(data.regime_meta).map(([r, m]) => ({
    regime: parseInt(r),
    ...m,
  })).sort((a, b) => b.sharpe - a.sharpe);

  return (
    <div className="space-y-5">
      {/* 헤더 */}
      <div>
        <h1 className="text-lg sm:text-xl font-semibold tracking-tight">시장 사이클 분석</h1>
        <p className="text-[11px] sm:text-[12px] text-[var(--text-muted)] mt-1">
          HMM 모델로 10년 데이터 학습. 4개 시장 국면 식별 + 국면별 역사적 우세 섹터 통계.
        </p>
      </div>

      {/* 현재 국면 카드 */}
      <div className={`bg-[var(--bg-card)] border ${curColor.border} rounded-2xl p-5 sm:p-6`}>
        <div className="flex items-baseline justify-between mb-3">
          <span className="text-[11px] text-[var(--text-muted)]">오늘의 시장 국면</span>
          <span className="text-[10px] text-[var(--text-muted)] num">{data.date} 기준</span>
        </div>
        <div className="flex items-center gap-3 mb-4">
          <span className={`inline-block w-2 h-2 rounded-full ${curColor.dot}`} />
          <span className={`text-[20px] sm:text-[24px] font-semibold ${curColor.text}`}>
            {regimeShort(cur.label)}
          </span>
          <span className="text-[14px] text-[var(--text-secondary)]">
            {regimeKorean(cur.label)}
          </span>
        </div>
        <div className="grid grid-cols-3 gap-2 text-[11px] sm:text-[12px]">
          <div>
            <div className="text-[var(--text-muted)] mb-0.5">과거 평균 비중</div>
            <div className="text-white font-medium num">{(cur.meta.pct_of_time * 100).toFixed(1)}%</div>
          </div>
          <div>
            <div className="text-[var(--text-muted)] mb-0.5">평균 지속</div>
            <div className="text-white font-medium num">{cur.meta.avg_duration_days.toFixed(0)}일</div>
          </div>
          <div>
            <div className="text-[var(--text-muted)] mb-0.5">과거 연수익률</div>
            <div className={`font-medium num ${cur.meta.annualized_return > 0 ? "positive" : "negative"}`}>
              {fmtPct(cur.meta.annualized_return, 1)}
            </div>
          </div>
        </div>
      </div>

      {/* 현재 국면 우세 섹터 */}
      <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-4 sm:p-5">
        <h3 className="text-[13px] sm:text-[14px] font-semibold text-white mb-1">
          이 국면 후 20일 평균 outperform 섹터 (역사적 통계)
        </h3>
        <p className="text-[10px] sm:text-[11px] text-[var(--text-muted)] mb-3">
          Test 데이터 (2022-2026) 기준 - 과거 통계이며 미래 수익을 보장하지 않습니다.
        </p>
        <div className="space-y-2">
          {curSectors.slice(0, 10).map((s, i) => (
            <div key={s.sector} className="flex items-center justify-between py-1.5 border-b border-white/[0.03] last:border-0">
              <div className="flex items-center gap-2.5">
                <span className="text-[var(--text-muted)] num text-[11px] w-5">{i + 1}</span>
                <span className="text-white text-[12px] sm:text-[13px]">{s.sector}</span>
              </div>
              <div className="flex items-center gap-3 text-[11px]">
                <span className="text-[var(--text-muted)] num">적중 {(s.hit_rate * 100).toFixed(0)}%</span>
                <span className={`num font-medium ${s.avg_20d > 0 ? "positive" : "negative"}`}>
                  {fmtPct(s.avg_20d, 2)}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 4 국면 비교 */}
      <div>
        <h3 className="text-[13px] sm:text-[14px] font-semibold text-white mb-2">4개 시장 국면 비교</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
          {regimeEntries.map((r) => {
            const key = regimeKey(r.label);
            const color = REGIME_COLOR[key];
            const isCurrent = r.regime === cur.regime;
            return (
              <div
                key={r.regime}
                className={`bg-[var(--bg-card)] border rounded-2xl p-3.5 ${
                  isCurrent ? `${color.border} ring-1 ring-${key.toLowerCase()}-500/20` : "border-white/[0.06]"
                }`}
              >
                <div className="flex items-center gap-1.5 mb-2">
                  <span className={`inline-block w-1.5 h-1.5 rounded-full ${color.dot}`} />
                  <span className={`text-[13px] font-semibold ${color.text}`}>
                    {regimeShort(r.label)}
                  </span>
                  {isCurrent && <span className="text-[9px] text-[var(--text-muted)] ml-auto">현재</span>}
                </div>
                <div className="text-[10px] text-[var(--text-muted)] mb-2">{regimeKorean(r.label)}</div>
                <div className="space-y-1.5 text-[11px]">
                  <div className="flex justify-between">
                    <span className="text-[var(--text-muted)]">연수익</span>
                    <span className={`num font-medium ${r.annualized_return > 0 ? "positive" : "negative"}`}>
                      {fmtPct(r.annualized_return, 1)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[var(--text-muted)]">변동성</span>
                    <span className="text-white num">{fmtPct(r.annualized_vol, 1)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[var(--text-muted)]">Sharpe</span>
                    <span className="text-white num">{r.sharpe.toFixed(2)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[var(--text-muted)]">비중</span>
                    <span className="text-white num">{(r.pct_of_time * 100).toFixed(0)}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-[var(--text-muted)]">지속</span>
                    <span className="text-white num">{r.avg_duration_days.toFixed(0)}일</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 국면별 우세 섹터 (전체) */}
      <div>
        <h3 className="text-[13px] sm:text-[14px] font-semibold text-white mb-2">국면별 역사적 우세 섹터 Top 5</h3>
        <p className="text-[10px] sm:text-[11px] text-[var(--text-muted)] mb-3">
          각 국면에서 향후 20영업일간 평균 outperform한 섹터 (Test 2022-2026, t-stat ≥ 5 통계 유의).
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {regimeEntries.map((r) => {
            const key = regimeKey(r.label);
            const color = REGIME_COLOR[key];
            const sectors = data.sectors_by_regime[String(r.regime)] || [];
            return (
              <div key={r.regime} className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-3.5">
                <div className="flex items-center gap-1.5 mb-2.5">
                  <span className={`inline-block w-1.5 h-1.5 rounded-full ${color.dot}`} />
                  <span className={`text-[12px] font-semibold ${color.text}`}>{regimeShort(r.label)}</span>
                  <span className="text-[10px] text-[var(--text-muted)]">{regimeKorean(r.label)}</span>
                </div>
                <div className="space-y-1.5">
                  {sectors.slice(0, 5).map((s, i) => (
                    <div key={s.sector} className="flex items-center justify-between text-[11px]">
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="text-[var(--text-muted)] num w-3">{i + 1}</span>
                        <span className="text-white truncate">{s.sector}</span>
                      </div>
                      <span className={`num font-medium shrink-0 ml-2 ${s.avg_20d > 0 ? "positive" : "negative"}`}>
                        {fmtPct(s.avg_20d, 2)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 방법론 */}
      <details className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-4 sm:p-5">
        <summary className="cursor-pointer text-[12px] sm:text-[13px] font-medium text-[var(--text-secondary)] hover:text-white">
          방법론 (HMM 모델 + 검증)
        </summary>
        <div className="mt-3 text-[11px] sm:text-[12px] text-[var(--text-secondary)] leading-relaxed space-y-2">
          <p>
            <span className="text-white font-medium">Hidden Markov Model (HMM)</span>로 시장의 4개 hidden state를 식별합니다.
            BIC criterion으로 2~4개 후보 중 4개가 최적으로 선택되었습니다.
          </p>
          <p>
            <span className="text-white font-medium">Features</span> (4개로 제한, parsimony):
            (1) 시장 20일 realized volatility, (2) 시장 20일 누적 수익률,
            (3) 섹터 간 cross-sectional dispersion, (4) 외인+기관 5일 flow z-score.
          </p>
          <p>
            <span className="text-white font-medium">Walk-forward validation</span>: Train 2017-2021 (1,189일) / Test 2022-2026 (1,076일).
            과최적화 방지를 위해 Train·Test sharpe 일관성을 검증했습니다.
          </p>
          <p>
            <span className="text-white font-medium">한계</span>: 본 통계는 과거 데이터 기반이며 미래 수익을 보장하지 않습니다.
            국면 라벨링은 통계적 분류이며, 실제 시장 단계와 정확히 일치하지 않을 수 있습니다.
            특히 Crisis 국면은 Test 표본 90일로 추정 신뢰도가 다른 국면보다 낮습니다.
          </p>
          <p className="text-[var(--text-muted)] pt-1">
            모델 학습 데이터: 2,327개 종목 × 10년 (2016-02 ~ 2026-05) × 24개 WICS 중분류 섹터.
            매일 cron으로 최신 국면 갱신됩니다.
          </p>
        </div>
      </details>
    </div>
  );
}
