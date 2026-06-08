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
  label_ko?: string;
  label_en?: string;
  pct_of_time: number;
  avg_duration_days: number;
  per_episode_return: number;  // 1회 평균 누적 수익률
  // 학술 metric (사이트엔 노출 X)
  annualized_return: number;
  annualized_vol: number;
  sharpe: number;
}
interface CurrentRegime {
  regime: number;
  label: string;
  label_ko?: string;
  label_en?: string;
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
        <h1 className="text-lg sm:text-xl font-semibold tracking-tight">시장 사이클</h1>
        <p className="text-[11px] sm:text-[12px] text-[var(--text-muted)] mt-1">
          시장이 강세장·안정기·조정기·하락기 4개 국면을 반복하는 패턴을 머신러닝으로 추정합니다.
          각 국면에서 과거에 강했던 섹터를 참고용으로 함께 보여줍니다.
        </p>
      </div>

      {/* 현재 국면 카드 — 단순화 (큰 숫자 + 짧은 설명) */}
      <div className={`bg-[var(--bg-card)] border ${curColor.border} rounded-2xl p-5 sm:p-6`}>
        <div className="flex items-baseline justify-between mb-3">
          <span className="text-[11px] text-[var(--text-muted)]">오늘의 시장 국면</span>
          <span className="text-[10px] text-[var(--text-muted)] num">{data.date} 기준</span>
        </div>
        <div className="flex items-center gap-2 mb-4">
          <span className={`inline-block w-2 h-2 rounded-full ${curColor.dot}`} />
          <span className={`text-[18px] sm:text-[20px] font-semibold ${curColor.text}`}>
            {cur.label_ko || regimeKorean(cur.label)}
          </span>
        </div>
        <div className="flex items-baseline gap-3 mb-2">
          <span className={`text-[36px] sm:text-[42px] font-bold num ${cur.meta.per_episode_return > 0 ? "positive" : "negative"} leading-none`}>
            {fmtPct(cur.meta.per_episode_return, 1)}
          </span>
          <span className="text-[12px] sm:text-[13px] text-[var(--text-secondary)]">
            보통 {cur.meta.avg_duration_days.toFixed(0)}일 지속
          </span>
        </div>
        <p className="text-[11px] text-[var(--text-muted)]">
          과거 10년 데이터에서 이 국면이 시작되면 평균 {cur.meta.avg_duration_days.toFixed(0)}영업일 동안 시장이 {cur.meta.per_episode_return > 0 ? "+" : ""}{(cur.meta.per_episode_return * 100).toFixed(1)}% 움직였습니다. 전체 기간 중 비중 {(cur.meta.pct_of_time * 100).toFixed(1)}%.
        </p>
      </div>

      {/* 현재 국면에서 과거 강세를 보인 섹터 */}
      <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-4 sm:p-5">
        <h3 className="text-[13px] sm:text-[14px] font-semibold text-white mb-1">
          이 국면에서 과거에 강세를 보인 섹터
        </h3>
        <p className="text-[10px] sm:text-[11px] text-[var(--text-muted)] mb-3">
          2022~2026년 데이터에서 이 국면 발생 후 20영업일 평균 상승률 상위 섹터 (과거 통계, 미래 수익을 보장하지 않습니다).
        </p>
        <div className="space-y-2">
          {curSectors.slice(0, 10).map((s, i) => (
            <Link
              key={s.sector}
              href={`/sectors/${encodeURIComponent(s.sector)}`}
              className="flex items-center justify-between py-1.5 border-b border-white/[0.03] last:border-0 hover:bg-white/[0.02] rounded transition px-1"
            >
              <div className="flex items-center gap-2.5">
                <span className="text-[var(--text-muted)] num text-[11px] w-5">{i + 1}</span>
                <span className="text-white text-[12px] sm:text-[13px]">{s.sector}</span>
              </div>
              <div className="flex items-center gap-3 text-[11px]">
                <span className="text-[var(--text-muted)] num">{(s.hit_rate * 100).toFixed(0)}% 상승</span>
                <span className={`num font-medium ${s.avg_20d > 0 ? "positive" : "negative"}`}>
                  {fmtPct(s.avg_20d, 2)}
                </span>
              </div>
            </Link>
          ))}
        </div>
      </div>

      {/* 4 국면 비교 — 단순화 (큰 숫자 + 지속·비중만) */}
      <div>
        <h3 className="text-[13px] sm:text-[14px] font-semibold text-white mb-2">4개 시장 국면</h3>
        <p className="text-[10px] sm:text-[11px] text-[var(--text-muted)] mb-3">
          각 국면이 시작되면 보통 N일 동안 시장이 이만큼 움직였습니다 (과거 10년 통계).
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
          {regimeEntries.map((r) => {
            const isCurrent = r.regime === cur.regime;
            const labelKo = (r as any).label_ko || regimeKorean(r.label);
            const labelKey = (r as any).label_en || regimeShort(r.label);
            const color = REGIME_COLOR[labelKey] || REGIME_COLOR.Quiet;
            return (
              <div
                key={r.regime}
                className={`bg-[var(--bg-card)] border rounded-2xl p-4 ${
                  isCurrent ? color.border : "border-white/[0.06]"
                }`}
              >
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-1.5">
                    <span className={`inline-block w-1.5 h-1.5 rounded-full ${color.dot}`} />
                    <span className={`text-[13px] sm:text-[14px] font-semibold ${color.text}`}>
                      {labelKo}
                    </span>
                  </div>
                  {isCurrent && <span className="text-[10px] text-[var(--text-muted)]">현재 국면</span>}
                </div>
                <div className="flex items-baseline gap-2 mb-1.5">
                  <span className={`text-[24px] sm:text-[28px] font-bold num leading-none ${r.per_episode_return > 0 ? "positive" : "negative"}`}>
                    {fmtPct(r.per_episode_return, 1)}
                  </span>
                  <span className="text-[11px] text-[var(--text-muted)]">
                    / {r.avg_duration_days.toFixed(0)}일
                  </span>
                </div>
                <div className="text-[10px] text-[var(--text-muted)]">
                  전체 기간 중 {(r.pct_of_time * 100).toFixed(0)}% 발생
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 국면별 강세 섹터 (전체 4국면) */}
      <div>
        <h3 className="text-[13px] sm:text-[14px] font-semibold text-white mb-2">국면별 강세 섹터 Top 5</h3>
        <p className="text-[10px] sm:text-[11px] text-[var(--text-muted)] mb-3">
          각 국면에서 과거에 가장 강한 상승을 보인 섹터 (20영업일 평균, 통계적으로 유의).
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {regimeEntries.map((r) => {
            const labelKo = (r as any).label_ko || regimeKorean(r.label);
            const labelKey = (r as any).label_en || regimeShort(r.label);
            const color = REGIME_COLOR[labelKey] || REGIME_COLOR.Quiet;
            const sectors = data.sectors_by_regime[String(r.regime)] || [];
            return (
              <div key={r.regime} className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-3.5">
                <div className="flex items-center gap-1.5 mb-2.5">
                  <span className={`inline-block w-1.5 h-1.5 rounded-full ${color.dot}`} />
                  <span className={`text-[12px] font-semibold ${color.text}`}>{labelKo}</span>
                </div>
                <div className="space-y-1.5">
                  {sectors.slice(0, 5).map((s, i) => (
                    <Link
                      key={s.sector}
                      href={`/sectors/${encodeURIComponent(s.sector)}`}
                      className="flex items-center justify-between text-[11px] hover:bg-white/[0.02] rounded transition px-1 py-0.5"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <span className="text-[var(--text-muted)] num w-3">{i + 1}</span>
                        <span className="text-white truncate">{s.sector}</span>
                      </div>
                      <span className={`num font-medium shrink-0 ml-2 ${s.avg_20d > 0 ? "positive" : "negative"}`}>
                        {fmtPct(s.avg_20d, 2)}
                      </span>
                    </Link>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 방법론 (간결) */}
      <details className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-4 sm:p-5">
        <summary className="cursor-pointer text-[12px] sm:text-[13px] font-medium text-[var(--text-secondary)] hover:text-white">
          이 분석은 어떻게 만들어졌나요?
        </summary>
        <div className="mt-3 text-[11px] sm:text-[12px] text-[var(--text-secondary)] leading-relaxed space-y-2">
          <p>
            과거 <span className="text-white font-medium">10년 시장 데이터 (2,300여 종목)</span>를 머신러닝(HMM)으로 분석해
            4개 국면으로 분류했습니다. 시장 변동성, 수익률, 섹터 분산, 외국인·기관 자금 흐름을 종합한 결과입니다.
          </p>
          <p>
            과최적화를 막기 위해 데이터를 2017~2021년(학습)과 2022~2026년(검증)으로 나눠 검증했습니다.
            국면별 패턴이 학습·검증 양쪽에서 유사하게 나타났습니다.
          </p>
          <p className="text-[var(--text-muted)]">
            <span className="text-white font-medium">한계</span>: 과거 통계이며 미래 수익을 보장하지 않습니다.
            특정 국면(고변동 하락기)은 표본이 다른 국면보다 적어 신뢰도가 상대적으로 낮습니다.
            매일 자동으로 최신 국면을 다시 계산합니다.
          </p>
        </div>
      </details>
    </div>
  );
}
