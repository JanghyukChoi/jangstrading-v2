"use client";

import { useEffect, useRef, useState } from "react";

/*
  캔들 + 거래량 차트.

  성능 규칙:
  - 이 파일은 next/dynamic(ssr:false)로만 불러온다. lightweight-charts 가 188KB 라
    메인 번들에 실리면 차트를 안 보는 사람까지 느려진다.
  - 데이터는 public/data/ohlc/{ticker}.json (종목당 8~13KB). timeseries 와 분리돼
    있어서 기존 페이지 로딩에는 영향이 없다.
  - 주봉/월봉은 일봉에서 즉석 집계한다. 서버에 세 벌을 두면 용량이 3배가 된다.

  일봉 데이터는 하루 한 번 갱신된다. 장중 실시간이 아니다 — 이 사이트는
  장 마감 후 확정 수급을 보는 곳이라 데이터 성격과 맞다.
*/

type Bar = { time: string; open: number; high: number; low: number; close: number };
type Vol = { time: string; value: number; color: string };
type Frame = "D" | "W" | "M";

interface Raw {
  t: string;
  d: number[]; // YYMMDD
  o: number[]; h: number[]; l: number[]; c: number[]; v: number[];
  /** 매물대 — [가격, 비중%]. fb=외국인, ib=기관 */
  fb?: [number, number][];
  ib?: [number, number][];
}

type Bucket = { price: number; weight: number; top: number; height: number };

/* 매물대 막대의 두께.

   구간 폭은 종목마다 다르다 — cost_basis 가 구간이 많으면 이웃끼리 합치기
   때문에 3%(기본)일 수도, 6%·9% 일 수도 있다. 서버에서 폭을 따로 안 받고
   막대 간격에서 되짚는다. 로그 등간격이라 이웃 간 최소 비율이 곧 구간 폭이다.
   고정 높이로 그리면 분포가 아니라 점선처럼 흩어져 보인다. */
function binHalf(src: [number, number][]): number {
  let r = Infinity;
  for (let i = 1; i < src.length; i++) {
    const q = src[i][0] / src[i - 1][0];
    if (q > 1 && q < r) r = q;
  }
  if (!isFinite(r)) r = 1.03;
  return (r - 1) / 2;
}

const UP = "#f04251";    // 한국 관행: 빨강 상승
const DOWN = "#3485fa";  // 파랑 하락

function toISO(yymmdd: number): string {
  const s = String(yymmdd).padStart(6, "0");
  return `20${s.slice(0, 2)}-${s.slice(2, 4)}-${s.slice(4, 6)}`;
}

/** 일봉을 주/월 단위로 묶는다. 시가=구간 첫날, 종가=마지막날, 고저=구간 최대/최소. */
function aggregate(raw: Raw, frame: Frame): { bars: Bar[]; vols: Vol[] } {
  const bars: Bar[] = [];
  const vols: Vol[] = [];
  if (!raw?.d?.length) return { bars, vols };

  const keyOf = (iso: string) => {
    if (frame === "D") return iso;
    const dt = new Date(iso + "T00:00:00Z");
    if (frame === "M") return iso.slice(0, 7);
    // 주: 해당 주 목요일 기준(ISO 주차와 동일한 그룹핑)
    const day = dt.getUTCDay() || 7;
    dt.setUTCDate(dt.getUTCDate() + 4 - day);
    return dt.toISOString().slice(0, 10);
  };

  let curKey = "";
  let acc: { iso: string; o: number; h: number; l: number; c: number; v: number } | null = null;

  for (let i = 0; i < raw.d.length; i++) {
    const iso = toISO(raw.d[i]);
    const k = keyOf(iso);
    if (k !== curKey) {
      if (acc) {
        bars.push({ time: acc.iso, open: acc.o, high: acc.h, low: acc.l, close: acc.c });
        vols.push({ time: acc.iso, value: acc.v, color: acc.c >= acc.o ? `${UP}55` : `${DOWN}55` });
      }
      curKey = k;
      acc = { iso, o: raw.o[i], h: raw.h[i], l: raw.l[i], c: raw.c[i], v: raw.v[i] };
    } else if (acc) {
      acc.h = Math.max(acc.h, raw.h[i]);
      acc.l = Math.min(acc.l, raw.l[i]);
      acc.c = raw.c[i];
      acc.v += raw.v[i];
      acc.iso = iso;
    }
  }
  if (acc) {
    bars.push({ time: acc.iso, open: acc.o, high: acc.h, low: acc.l, close: acc.c });
    vols.push({ time: acc.iso, value: acc.v, color: acc.c >= acc.o ? `${UP}55` : `${DOWN}55` });
  }
  return { bars, vols };
}

export default function PriceChart({
  ticker,
  foreignAvg,
  institutionAvg,
}: {
  ticker: string;
  foreignAvg?: number | null;
  institutionAvg?: number | null;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [raw, setRaw] = useState<Raw | null>(null);
  const [frame, setFrame] = useState<Frame>("D");
  const [state, setState] = useState<"loading" | "ready" | "empty">("loading");
  const [showBasis, setShowBasis] = useState(true);
  // 매물대 막대는 차트 좌표계에 얹어야 해서, 가격->y좌표 변환 후 위치를 잡는다.
  const [buckets, setBuckets] = useState<Bucket[]>([]);

  useEffect(() => {
    let alive = true;
    fetch(`/data/ohlc/${ticker}.json`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d: Raw | null) => {
        if (!alive) return;
        if (!d?.d?.length) { setState("empty"); return; }
        setRaw(d);
        setState("ready");
      })
      .catch(() => alive && setState("empty"));
    return () => { alive = false; };
  }, [ticker]);

  useEffect(() => {
    if (state !== "ready" || !raw || !box.current) return;
    let disposed = false;
    let chart: any = null;
    let raf = 0;

    (async () => {
      const LWC = await import("lightweight-charts");
      if (disposed || !box.current) return;

      chart = LWC.createChart(box.current, {
        layout: {
          background: { color: "transparent" },
          textColor: "#9e9ea4",
          fontFamily: "Pretendard Variable, Pretendard, system-ui, sans-serif",
        },
        grid: {
          vertLines: { color: "rgba(255,255,255,0.04)" },
          horzLines: { color: "rgba(255,255,255,0.04)" },
        },
        rightPriceScale: { borderColor: "rgba(255,255,255,0.08)" },
        timeScale: { borderColor: "rgba(255,255,255,0.08)", rightOffset: 4 },
        crosshair: { mode: LWC.CrosshairMode.Normal },
        localization: {
          locale: "ko-KR",
          priceFormatter: (p: number) => Math.round(p).toLocaleString("ko-KR"),
        },
        height: 340,
        autoSize: true,
      });

      const { bars, vols } = aggregate(raw, frame);

      const candle = chart.addSeries(LWC.CandlestickSeries, {
        upColor: UP, downColor: DOWN,
        borderUpColor: UP, borderDownColor: DOWN,
        wickUpColor: UP, wickDownColor: DOWN,
        // 현재가 선이 빨강이면 외국인 평균선과 같은 색이라 구분이 안 된다.
        // 중립 회색으로 빼서 셋이 서로 다르게 보이도록 한다.
        priceLineColor: "#9e9ea4",
        priceLineWidth: 1,
      });
      candle.setData(bars);
      candle.priceScale().applyOptions({ scaleMargins: { top: 0.08, bottom: 0.28 } });

      const volume = chart.addSeries(LWC.HistogramSeries, {
        priceFormat: { type: "volume" },
        priceScaleId: "vol",
      });
      volume.setData(vols);
      chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.78, bottom: 0 } });

      // 외국인·기관 추정 평균 매입가 — 이 사이트의 차별점.
      // 다른 차트에는 없는 선이다.
      const lines: [number | null | undefined, string, string][] = [
        [foreignAvg, UP, "외국인 평균"],
        [institutionAvg, DOWN, "기관 평균"],
      ];
      for (const [price, color, title] of lines) {
        if (!price || price <= 0) continue;
        candle.createPriceLine({
          price, color, lineWidth: 1,
          lineStyle: LWC.LineStyle.Dashed,
          axisLabelVisible: true, title,
        });
      }

      chart.timeScale().fitContent();

      // 매물대: 가격을 y좌표로 바꿔 오버레이 막대를 놓는다.
      // lightweight-charts 에 volume-profile 이 없어서 직접 얹는다.
      //
      // 가격축을 드래그해 스케일을 바꾸면 timeScale 이벤트가 안 온다. 그래서
      // 매 프레임 좌표를 다시 재고, 실제로 바뀐 경우에만 상태를 갱신한다
      // (12~28개 변환이라 비용이 거의 없다). 확대·축소·리사이즈·자동스케일이
      // 전부 이 한 경로로 잡힌다.
      const src = raw.fb?.length ? raw.fb : raw.ib;
      const half = src?.length ? binHalf(src) : 0.015;
      let prevKey = "";
      const tick = () => {
        if (disposed) return;
        if (src?.length) {
          const next: Bucket[] = [];
          for (const [price, weight] of src) {
            const yTop = candle.priceToCoordinate(price * (1 + half));
            const yBot = candle.priceToCoordinate(price * (1 - half));
            if (yTop == null || yBot == null) continue;
            next.push({
              price, weight,
              top: yTop,
              height: Math.max(2, Math.abs(yBot - yTop) - 1),
            });
          }
          const key = next.map((b) => `${b.top.toFixed(1)}:${b.height.toFixed(1)}`).join(",");
          if (key !== prevKey) { prevKey = key; setBuckets(next); }
        }
        raf = requestAnimationFrame(tick);
      };
      raf = requestAnimationFrame(tick);
    })();

    return () => {
      disposed = true;
      if (raf) cancelAnimationFrame(raf);
      if (chart) chart.remove();
    };
  }, [state, raw, frame, foreignAvg, institutionAvg]);

  const maxWeight = buckets.reduce((m, b) => Math.max(m, b.weight), 0) || 1;

  if (state === "empty") return null;

  return (
    <div className="bg-[var(--bg-card)] rounded-2xl p-4 sm:p-6">
      <div className="flex items-center justify-between mb-4 gap-3">
        <div>
          <h3 className="text-[15px] sm:text-[17px] font-semibold text-white">주가 차트</h3>
          <p className="text-[12px] text-[var(--text-muted)] mt-0.5">
            점선은 추정 평균 매입가 · 오른쪽 막대는 매물대
          </p>
        </div>
        <div className="flex rounded-lg overflow-hidden bg-[var(--bg-sunken)] shrink-0">
          {([["D", "일"], ["W", "주"], ["M", "월"]] as const).map(([k, label]) => (
            <button
              key={k}
              onClick={() => setFrame(k)}
              className={`px-2.5 sm:px-3 py-[5px] sm:py-[7px] text-[12px] sm:text-[13px] transition-all ${
                frame === k
                  ? "bg-[var(--accent-blue)] text-white font-medium"
                  : "text-[var(--text-secondary)] hover:text-white"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {state === "loading" ? (
        <div className="h-[340px] rounded-xl bg-white/[0.02] animate-pulse" />
      ) : (
        <div className="relative">
          <div ref={box} className="h-[340px] w-full" />
          {showBasis && buckets.length > 0 && (
            <div className="pointer-events-none absolute inset-y-0 right-[58px] w-[86px]">
              {buckets.map((b) => (
                <div
                  key={b.price}
                  className="absolute right-0 rounded-l-[2px]"
                  style={{
                    top: `${b.top}px`,
                    height: `${b.height}px`,
                    width: `${Math.max(8, (b.weight / maxWeight) * 100)}%`,
                    background: `${UP}4d`,
                  }}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {buckets.length > 0 && (
        <button
          onClick={() => setShowBasis((v) => !v)}
          className="mt-3 text-[12px] text-[var(--text-muted)] hover:text-white transition"
        >
          매물대 {showBasis ? "숨기기" : "보기"}
        </button>
      )}
    </div>
  );
}
