"use client";

import { useEffect, useMemo, useState } from "react";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceLine,
} from "recharts";

/* ── 타입 ─────────────────────────────────────── */
interface Series {
  dates: string[];
  mcap: number[];
  netinc: number[];
  per: (number | null)[];
  roe: (number | null)[];
  priceIdx: number[];
  earnIdx: (number | null)[];
}
type Lvl = "large" | "mid";
type View = "pe" | "per" | "roe";

const LVL_LABEL: Record<Lvl, string> = { large: "대분류", mid: "중분류" };
const VIEW_LABEL: Record<View, string> = { pe: "가격 vs 실적", per: "PER 추이", roe: "ROE 추이" };

function pct(a: number, b: number | null | undefined) {
  if (b == null || b === 0) return null;
  return (a / b - 1) * 100;
}
/* 반올림 후 "-0" 방지한 정수% 문자열 */
function fp(x: number | null | undefined) {
  if (x == null) return "0";
  const r = Math.round(x);
  return Object.is(r, -0) ? "0" : String(r);
}

/* ── 자동 해석 ─────────────────────────────────── */
function interpret(s: Series) {
  const n = s.dates.length;
  const i0 = Math.max(0, n - 5); // ~1년 전 (분기 4개)
  const pChg = pct(s.priceIdx[n - 1], s.priceIdx[i0]);
  const eNow = s.earnIdx[n - 1], ePrev = s.earnIdx[i0];
  const eChg = eNow != null && ePrev != null ? pct(eNow, ePrev) : null;

  const pers = s.per.filter((x): x is number => x != null && x > 0);
  const curPer = s.per[n - 1];
  let perPctile: number | null = null;
  if (curPer != null && curPer > 0 && pers.length > 5) {
    perPctile = (pers.filter((x) => x < curPer).length / pers.length) * 100;
  }

  let title = "", tone = "neutral", body = "";
  if (eChg == null) {
    title = "실적 적자 구간";
    body = "섹터 합산 순이익이 적자라 PER 해석이 어렵습니다. 흑자 전환 여부가 관건.";
    tone = "warn";
  } else if (pChg != null && pChg > 15 && eChg < pChg - 15) {
    title = "가격이 실적을 앞서감";
    tone = "warn";
    body = `최근 1년 가격 ${fp(pChg)}% vs 실적 ${fp(eChg)}%. 밸류에이션(기대)이 실적보다 빠르게 확장 — 실적이 따라와야 정당화됩니다.`;
  } else if (eChg > 15 && (pChg == null || eChg > pChg + 15)) {
    title = "실적이 가격을 앞섬 (저평가 여지)";
    tone = "good";
    body = `최근 1년 실적 ${fp(eChg)}% vs 가격 ${fp(pChg)}%. 실적 개선을 가격이 아직 덜 반영.`;
  } else if (pChg != null && pChg < -10 && eChg < -10) {
    title = "실적·가격 동반 약화";
    tone = "bad";
    body = `가격 ${fp(pChg)}% · 실적 ${fp(eChg)}% 동반 하락 — 구조적 부진. 단순 저PER이 아니라 밸류트랩 주의.`;
  } else {
    title = "실적이 가격을 받쳐줌";
    tone = "good";
    body = `가격과 실적이 함께 움직이는 건강한 구간 (가격 ${fp(pChg)}% · 실적 ${fp(eChg)}%).`;
  }
  return { title, tone, body, perPctile, curPer };
}

const TONE: Record<string, string> = {
  good: "border-[#3fb950]/30 bg-[#3fb950]/[0.06]",
  warn: "border-[#d29922]/30 bg-[#d29922]/[0.06]",
  bad: "border-[#f85149]/30 bg-[#f85149]/[0.06]",
  neutral: "border-white/[0.08] bg-white/[0.02]",
};

/* ── 컴포넌트 ─────────────────────────────────── */
export default function SectorFundamentals({ sectorName }: { sectorName?: string }) {
  const [data, setData] = useState<{ asof: string; levels: Record<string, Record<string, Series>> } | null>(null);
  const [lvl, setLvl] = useState<Lvl>("mid");
  const [userSec, setUserSec] = useState<string>("");
  const [view, setView] = useState<View>("pe");

  useEffect(() => {
    fetch("/data/sector-fundamentals.json").then((r) => r.json()).then(setData).catch(() => {});
  }, []);

  const detail = sectorName != null;
  const sectors = useMemo(() => (data && !detail ? Object.keys(data.levels[lvl]).sort() : []), [data, lvl, detail]);
  const browseSec = userSec && sectors.includes(userSec) ? userSec : (sectors.find((x) => x.includes("반도체")) || sectors[0] || "");

  if (!data) return null;

  // 상세모드: 이름으로 large→mid→theme 검색 / 브라우즈모드: 셀렉터
  let s: Series | undefined;
  if (detail) {
    for (const lv of ["large", "mid", "theme"]) {
      if (data.levels[lv]?.[sectorName!]) { s = data.levels[lv][sectorName!]; break; }
    }
  } else {
    s = data.levels[lvl][browseSec];
  }
  if (!s) return null;

  const rows = s.dates.map((d, i) => ({ date: d, price: s!.priceIdx[i], earn: s!.earnIdx[i], per: s!.per[i], roe: s!.roe[i] }));
  const info = interpret(s);
  const last = s.dates.length - 1;

  const numOf = (xs: (number | null)[]) => xs.filter((v): v is number => typeof v === "number" && isFinite(v));
  const peVals = numOf([...s.priceIdx, ...s.earnIdx]).filter((v) => v > 0);
  const perVals = numOf(s.per); const roeVals = numOf(s.roe);
  const perSorted = [...perVals].sort((a, b) => a - b);
  const perMed = perSorted.length ? perSorted[Math.floor(perSorted.length / 2)] : 15;
  const perCap = Math.max(30, perMed * 3);
  // 상단 라벨 잘림 방지: 도메인 최댓값을 깔끔한 단위로 올림
  const niceCeil = (x: number) => {
    if (x <= 0) return 1;
    const mag = Math.pow(10, Math.floor(Math.log10(x)));
    const step = mag <= 5 ? 1 : mag / 5; // 작은 값은 1단위, 큰 값은 비례 단위
    return Math.ceil(x / step) * step;
  };
  const roeMax = roeVals.length ? Math.max(...roeVals) : 10;
  const roeMin = Math.min(0, ...(roeVals.length ? roeVals : [0]));
  const yDomain: [number, number] =
    view === "pe" ? [Math.max(1, Math.min(...peVals) * 0.9), niceCeil(Math.max(...peVals) * 1.05)]
    : view === "per" ? [0, perCap]
    : [roeMin < 0 ? -niceCeil(-roeMin) : 0, niceCeil(roeMax)];

  const fmtX = (d: string) => d.slice(2, 4) + "." + d.slice(5, 7);

  return (
    <div className="bg-[var(--bg-card)] border border-white/[0.06] rounded-2xl p-4 sm:p-5 mb-6">
      {/* 헤더 */}
      <div className="flex items-start justify-between gap-2 mb-3 flex-wrap">
        <div>
          <h3 className="text-sm sm:text-base font-semibold tracking-tight">{detail ? `${sectorName} · 실적 vs 가격` : "섹터 실적 vs 가격"}</h3>
          <p className="text-[11px] text-[var(--text-muted)] mt-0.5">밸류에이션이 실적으로 정당화되는지 — 가격과 이익을 분리해서</p>
        </div>
        {!detail && (
          <div className="flex items-center gap-2 flex-wrap">
            <div className="inline-flex rounded-lg border border-white/[0.06] overflow-hidden">
              {(Object.keys(LVL_LABEL) as Lvl[]).map((k) => (
                <button key={k} onClick={() => setLvl(k)}
                  className={`px-2.5 py-1 text-[11px] cursor-pointer border-none ${lvl === k ? "bg-white/[0.1] text-white font-medium" : "bg-transparent text-[var(--text-secondary)] hover:text-white"}`}>
                  {LVL_LABEL[k]}
                </button>
              ))}
            </div>
            <select value={browseSec} onChange={(e) => setUserSec(e.target.value)}
              className="bg-[var(--bg-card)] border border-white/[0.06] rounded-lg px-2.5 py-[5px] text-[11px] text-[var(--text-secondary)] outline-none cursor-pointer max-w-[160px]">
              {sectors.map((x) => <option key={x} value={x}>{x}</option>)}
            </select>
          </div>
        )}
      </div>

      {/* 자동 해석 */}
      <div className={`rounded-xl border px-3 py-2.5 mb-3 ${TONE[info.tone]}`}>
        <div className="text-[12.5px] font-semibold text-white">{info.title}</div>
        <div className="text-[11.5px] text-[var(--text-secondary)] leading-relaxed mt-0.5">{info.body}</div>
        {info.curPer != null && info.perPctile != null && (
          <div className="text-[11px] text-[var(--text-muted)] mt-1">
            현재 PER <span className="num text-[var(--text-secondary)]">{info.curPer}배</span> · 10년 범위의 <span className="num text-[var(--text-secondary)]">{info.perPctile.toFixed(0)}%</span> 지점{info.perPctile > 75 ? " (역사적 고평가권)" : info.perPctile < 25 ? " (역사적 저평가권)" : ""}
          </div>
        )}
      </div>

      {/* 뷰 토글 */}
      <div className="inline-flex rounded-lg border border-white/[0.06] overflow-hidden mb-2">
        {(Object.keys(VIEW_LABEL) as View[]).map((k) => (
          <button key={k} onClick={() => setView(k)}
            className={`px-3 py-1 text-[11px] cursor-pointer border-none ${view === k ? "bg-[#4a8fe7] text-white font-medium" : "bg-transparent text-[var(--text-secondary)] hover:text-white"}`}>
            {VIEW_LABEL[k]}
          </button>
        ))}
      </div>

      {/* 차트 */}
      <div style={{ height: 300 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 14, right: 8, left: -8, bottom: 0 }}>
            <CartesianGrid stroke="rgba(255,255,255,0.04)" vertical={false} />
            <XAxis dataKey="date" tickFormatter={fmtX} tick={{ fontSize: 10, fill: "var(--text-muted)" }}
              minTickGap={40} axisLine={false} tickLine={false} />
            <YAxis scale={view === "pe" ? "log" : "linear"} domain={yDomain} allowDataOverflow={view === "per"}
              tick={{ fontSize: 10, fill: "var(--text-muted)" }} axisLine={false} tickLine={false} width={40}
              tickFormatter={(v) => (view === "roe" ? `${v}%` : `${Math.round(v)}`)} />
            <Tooltip contentStyle={{ background: "rgba(12,14,20,0.95)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 10, fontSize: 12 }}
              labelStyle={{ color: "#fff" }}
              formatter={(v, name) => [v == null ? "-" : (view === "roe" ? `${v}%` : view === "per" ? `${v}배` : v), name]} />
            {view === "pe" && <Line type="linear" dataKey="price" name="가격지수" stroke="#4a8fe7" strokeWidth={2} dot={false} isAnimationActive={false} />}
            {view === "pe" && <Line type="linear" dataKey="earn" name="실적지수" stroke="#e3b341" strokeWidth={2} dot={false} isAnimationActive={false} connectNulls />}
            {view === "per" && <Line type="linear" dataKey="per" name="PER" stroke="#a371f7" strokeWidth={2} dot={false} isAnimationActive={false} connectNulls />}
            {view === "roe" && <Line type="linear" dataKey="roe" name="ROE" stroke="#3fb950" strokeWidth={2} dot={false} isAnimationActive={false} connectNulls />}
            {view === "per" && <ReferenceLine y={s.per[last] ?? undefined} stroke="rgba(255,255,255,0.12)" strokeDasharray="3 3" />}
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* 현재 스냅 */}
      <div className="grid grid-cols-4 gap-2 mt-3 text-center">
        {[
          { l: "시총", v: `${s.mcap[last].toFixed(0)}조` },
          { l: "순이익(TTM)", v: `${s.netinc[last].toFixed(1)}조` },
          { l: "PER", v: s.per[last] != null ? `${s.per[last]}배` : "적자" },
          { l: "ROE", v: s.roe[last] != null ? `${s.roe[last]}%` : "-" },
        ].map((x) => (
          <div key={x.l} className="bg-white/[0.02] rounded-lg py-2">
            <div className="text-[10px] text-[var(--text-muted)]">{x.l}</div>
            <div className="num text-[13px] text-white font-medium mt-0.5">{x.v}</div>
          </div>
        ))}
      </div>

      {view === "pe" && (
        <p className="text-[10px] text-[var(--text-muted)] mt-3 leading-relaxed">
          <span className="text-[#4a8fe7]">가격지수</span>·<span className="text-[#e3b341]">실적지수</span> 모두 시작점 100 기준 · 둘이 벌어지면 밸류에이션 확장(가격↑)/축소 · 실적=섹터 합산 순이익(TTM) · 분기 데이터 · 분할보정 · {data.asof} 기준
        </p>
      )}
      {view === "per" && (
        <p className="text-[10px] text-[var(--text-muted)] mt-3 leading-relaxed">
          ⚠️ 경기민감 섹터는 <b className="text-[var(--text-secondary)]">실적이 바닥일 때 PER이 급등</b>합니다(시총÷순이익에서 분모↓). 그 구간엔 <b className="text-[var(--text-secondary)]">ROE</b>가 더 신뢰성 높음. (상위 스파이크는 축에서 잘림)
        </p>
      )}
      {view === "roe" && (
        <p className="text-[10px] text-[var(--text-muted)] mt-3 leading-relaxed">
          ROE = 섹터 합산 순이익 ÷ 자기자본 · 수익성·턴어라운드 (PER과 달리 실적 바닥에서도 안정적) · {data.asof} 기준
        </p>
      )}
    </div>
  );
}
