"use client";

import { useEffect, useRef, useState, useCallback } from "react";

/* ── 타입 ──────────────────────────────────────── */
interface RRGSector {
  n: string; // 중분류 이름
  l: string; // 대분류
  t: number[][]; // trail [[x,y], ...]
  f: number; // 기간 누적 수급 (백만원)
}

type Period = "1d" | "1w" | "1m" | "3m" | "6m";
type Investor = "combined" | "foreign" | "institution" | "pension";

const INVESTOR_LABELS: Record<Investor, string> = {
  combined: "외국인+기관 합산",
  foreign: "외국인",
  institution: "기관",
  pension: "연기금",
};

const COLORS: Record<string, string> = {
  IT: "#7EB5E8",
  금융: "#8DC462",
  경기관련소비재: "#ED9872",
  건강관리: "#E88EAE",
  산업재: "#AAA9A3",
  소재: "#A9A3E6",
  커뮤니케이션서비스: "#F5C26A",
  필수소비재: "#56C59D",
  에너지: "#F2B5B5",
  유틸리티: "#92DABD",
};

const PAD = { t: 28, r: 28, b: 36, l: 28 };

/* ── 금액 포맷 (백만원 → 억원/조) ────────────── */
function fmtFlow(v: number) {
  const a = Math.abs(v);
  const s = v > 0 ? "+" : "";
  if (a >= 1_000_000) return `${s}${(v / 1_000_000).toFixed(1)}조`;
  if (a >= 100) return `${s}${Math.round(v / 100).toLocaleString()}억원`;
  return `${s}${Math.round(v)}백만`;
}

/* ── 컴포넌트 ─────────────────────────────────── */
type Level = "large" | "mid";

export default function SectorRRG({ level, period, investor }: { level: Level; period: Period; investor: Investor }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  // data: { investor: { level: { period: [...] } } }
  const [data, setData] = useState<Record<string, Record<string, Record<string, RRGSector[]>>> | null>(null);
  const [sel, setSel] = useState(-1);
  const [wrapW, setWrapW] = useState(0); // 컨테이너 너비 (툴팁 클램프·반응형 높이용)
  const [tip, setTip] = useState<{
    show: boolean;
    x: number;
    y: number;
    sector: RRGSector;
    quadrant: string;
  } | null>(null);

  // 투자자·분류레벨·기간이 바뀌면 선택/툴팁 초기화 (렌더 단계 reset — effect보다 안전)
  const selKey = `${investor}-${level}-${period}`;
  const [prevKey, setPrevKey] = useState(selKey);
  if (prevKey !== selKey) {
    setPrevKey(selKey);
    setSel(-1);
    setTip(null);
  }

  // 모바일에선 높이를 낮춰 세로로 길쭉해지지 않게
  const chartH = wrapW > 0 && wrapW < 480 ? 400 : 500;

  // 내부 상태 ref (Canvas 이벤트에서 접근)
  const stateRef = useRef<{
    data: RRGSector[];
    sx: (v: number) => number;
    sy: (v: number) => number;
  } | null>(null);

  /* ── 데이터 로드 ─────────────────────────────── */
  useEffect(() => {
    fetch("/data/rrg-data.json")
      .then((r) => r.json())
      .then(setData)
      .catch(() => {});
  }, []);

  /* ── 컨테이너 너비 추적 (ResizeObserver) ──────── */
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setWrapW(el.clientWidth));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  /* ── 그리기 ──────────────────────────────────── */
  const draw = useCallback(() => {
    const cv = canvasRef.current;
    if (!cv || !data) return;
    const ctx = cv.getContext("2d");
    if (!ctx) return;

    const sectors = data[investor]?.[level]?.[period];
    if (!sectors?.length) return;

    const dpr = window.devicePixelRatio || 1;
    const wrap = wrapRef.current;
    const W_CSS = wrapW || wrap?.clientWidth || 700;
    const H_CSS = W_CSS < 480 ? 400 : 500;
    cv.width = W_CSS * dpr;
    cv.height = H_CSS * dpr;
    cv.style.width = `${W_CSS}px`;
    cv.style.height = `${H_CSS}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W_CSS, H_CSS);

    const W = W_CSS;
    const H = H_CSS;

    // 축 범위 계산
    const ax: number[] = [];
    const ay: number[] = [];
    sectors.forEach((d) => {
      const last = d.t[d.t.length - 1];
      ax.push(last[0]);
      ay.push(last[1]);
    });
    if (sel >= 0 && sel < sectors.length) {
      sectors[sel].t.forEach((p) => {
        ax.push(p[0]);
        ay.push(p[1]);
      });
    }
    ax.sort((a, b) => a - b);
    ay.sort((a, b) => a - b);

    const pc = (arr: number[], p: number) => arr[Math.floor(arr.length * p)] || 0;
    let x0 = pc(ax, 0.03),
      x1 = pc(ax, 0.97),
      y0 = pc(ay, 0.03),
      y1 = pc(ay, 0.97);
    const xr = (x1 - x0) || 100;
    const yr = (y1 - y0) || 100;
    x0 -= xr * 0.25;
    x1 += xr * 0.25;
    y0 -= yr * 0.25;
    y1 += yr * 0.25;

    const sx = (v: number) =>
      PAD.l + Math.max(0, Math.min(1, (v - x0) / (x1 - x0))) * (W - PAD.l - PAD.r);
    const sy = (v: number) =>
      PAD.t + Math.max(0, Math.min(1, (y1 - v) / (y1 - y0))) * (H - PAD.t - PAD.b);

    stateRef.current = { data: sectors, sx, sy };

    const zx = sx(0);
    const zy = sy(0);

    // 사분면
    ctx.globalAlpha = 0.11;
    ctx.fillStyle = "#34b464"; ctx.fillRect(zx, PAD.t, W - PAD.r - zx, zy - PAD.t);
    ctx.fillStyle = "#d05040"; ctx.fillRect(PAD.l, PAD.t, zx - PAD.l, zy - PAD.t);
    ctx.fillStyle = "#4080d0"; ctx.fillRect(PAD.l, zy, zx - PAD.l, H - PAD.b - zy);
    ctx.fillStyle = "#c0a030"; ctx.fillRect(zx, zy, W - PAD.r - zx, H - PAD.b - zy);
    ctx.globalAlpha = 1;

    // 축선
    ctx.strokeStyle = "rgba(255,255,255,.16)";
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(zx, PAD.t); ctx.lineTo(zx, H - PAD.b); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(PAD.l, zy); ctx.lineTo(W - PAD.r, zy); ctx.stroke();

    // 사분면 라벨
    ctx.font = "600 12px var(--font-sans, sans-serif)";
    ctx.globalAlpha = 0.6;
    ctx.textAlign = "right"; ctx.fillStyle = "#6fc48a"; ctx.fillText("적극 매집", W - PAD.r - 6, PAD.t + 16);
    ctx.textAlign = "left"; ctx.fillStyle = "#e08070"; ctx.fillText("관심 전환", PAD.l + 6, PAD.t + 16);
    ctx.fillStyle = "#78a8e0"; ctx.fillText("적극 이탈", PAD.l + 6, H - PAD.b - 8);
    ctx.textAlign = "right"; ctx.fillStyle = "#c9b85a"; ctx.fillText("매집 둔화", W - PAD.r - 6, H - PAD.b - 8);
    ctx.globalAlpha = 1;

    // 축 라벨
    ctx.font = "11px var(--font-sans, sans-serif)";
    ctx.textAlign = "center";
    ctx.fillStyle = "rgba(255,255,255,.4)";
    ctx.fillText("← 순유출  |  수급 강도 (시총대비%)  |  순유입 →", W / 2, H - 6);
    ctx.save();
    ctx.translate(10, H / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText("← 감속  |  수급 가속도  |  가속 →", 0, 0);
    ctx.restore();

    const has = sel >= 0 && sel < sectors.length;
    const isMobile = W < 480;

    // 비선택 점 그리기
    sectors.forEach((d, i) => {
      if (i === sel) return;
      const cl = COLORS[d.l] || "#888";
      const last = d.t[d.t.length - 1];
      const px = sx(last[0]);
      const py = sy(last[1]);

      ctx.globalAlpha = has ? 0.15 : 0.75;
      ctx.beginPath();
      ctx.arc(px, py, has ? 3 : 5, 0, Math.PI * 2);
      ctx.fillStyle = cl;
      ctx.fill();
      ctx.strokeStyle = "rgba(0,0,0,.3)";
      ctx.lineWidth = 0.6;
      ctx.stroke();
      ctx.globalAlpha = 1;
    });

    // 라벨 패스 (선택 없을 때만): 원점에서 먼 점부터 그린다.
    // A) 위치 기반 정렬 — 오른쪽 끝 점은 라벨을 점 왼쪽으로(우측 앵커), 왼쪽 끝은 오른쪽으로.
    //    measureText 폭에 의존하지 않으므로 폰트 측정 오차와 무관하게 잘리지 않음.
    // B) 모바일은 라벨 4개·10px, 데스크톱은 8개·11px
    // C) 이미 그린 라벨과 겹치면 건너뛰기
    if (!has) {
      const maxLabels = isMobile ? 4 : 8;
      const fontPx = isMobile ? 10 : 11;
      ctx.font = `${fontPx}px var(--font-sans, sans-serif)`;
      ctx.fillStyle = "rgba(255,255,255,.5)";

      const rightZone = W - PAD.r - 70;
      const leftZone = PAD.l + 70;

      const cands = sectors
        .map((d, i) => {
          const l = d.t[d.t.length - 1];
          return { d, i, dist: Math.hypot(l[0], l[1]) };
        })
        .filter((c) => c.i !== sel)
        .sort((a, b) => b.dist - a.dist)
        .slice(0, maxLabels);

      const placed: { x0: number; y0: number; x1: number; y1: number }[] = [];
      for (const c of cands) {
        const last = c.d.t[c.d.t.length - 1];
        const px = sx(last[0]);
        const py = sy(last[1]);
        let lb = c.d.n;
        if (lb.length > 10) lb = lb.slice(0, 10) + "…";
        const lw = ctx.measureText(lb).width;

        // 위치에 따라 정렬·앵커 결정 (앵커는 항상 캔버스 안)
        let align: CanvasTextAlign, anchorX: number, x0: number, x1: number;
        if (px > rightZone) {
          align = "right"; anchorX = Math.min(px, W - PAD.r);
          x1 = anchorX; x0 = anchorX - lw;
        } else if (px < leftZone) {
          align = "left"; anchorX = Math.max(px, PAD.l);
          x0 = anchorX; x1 = anchorX + lw;
        } else {
          align = "center"; anchorX = px;
          x0 = anchorX - lw / 2; x1 = anchorX + lw / 2;
        }
        const top = py - 9 - fontPx;
        const box = { x0, y0: top, x1, y1: top + fontPx + 2 };
        const hit = placed.some(
          (p) => !(box.x1 < p.x0 || box.x0 > p.x1 || box.y1 < p.y0 || box.y0 > p.y1)
        );
        if (hit) continue;
        placed.push(box);
        ctx.textAlign = align;
        ctx.fillText(lb, anchorX, py - 9);
      }
    }

    // 선택된 섹터: 궤적 + 점
    if (has) {
      const d = sectors[sel];
      const cl = COLORS[d.l] || "#888";
      const t = d.t;
      const n = t.length;

      if (n >= 2) {
        ctx.beginPath();
        t.forEach((p, j) => {
          const px = sx(p[0]), py = sy(p[1]);
          if (j === 0) ctx.moveTo(px, py);
          else ctx.lineTo(px, py);
        });
        ctx.strokeStyle = cl;
        ctx.globalAlpha = 0.85;
        ctx.lineWidth = 2.5;
        ctx.stroke();
        ctx.globalAlpha = 1;
      }

      t.forEach((p, j) => {
        if (j === n - 1) return;
        const px = sx(p[0]), py = sy(p[1]);
        ctx.globalAlpha = 0.2 + (j / (n - 1)) * 0.6;
        ctx.beginPath(); ctx.arc(px, py, 4, 0, Math.PI * 2);
        ctx.fillStyle = cl; ctx.fill();
        ctx.strokeStyle = "rgba(255,255,255,.15)"; ctx.lineWidth = 0.5; ctx.stroke();
        ctx.globalAlpha = 1;
      });

      const last = t[n - 1];
      const px = sx(last[0]), py = sy(last[1]);
      ctx.beginPath(); ctx.arc(px, py, 9, 0, Math.PI * 2);
      ctx.fillStyle = cl; ctx.fill();
      ctx.strokeStyle = "rgba(255,255,255,.25)"; ctx.lineWidth = 2; ctx.stroke();

      // 글로우
      ctx.beginPath(); ctx.arc(px, py, 14, 0, Math.PI * 2);
      ctx.strokeStyle = cl; ctx.globalAlpha = 0.15; ctx.lineWidth = 3; ctx.stroke();
      ctx.globalAlpha = 1;

      // 화살표
      if (n >= 2) {
        const prev = t[n - 2];
        const dx = px - sx(prev[0]);
        const dy = py - sy(prev[1]);
        const len = Math.sqrt(dx * dx + dy * dy);
        if (len > 4) {
          const ux = dx / len, uy = dy / len;
          const apx = px + ux * 14, apy = py + uy * 14;
          ctx.beginPath();
          ctx.moveTo(apx, apy);
          ctx.lineTo(apx - ux * 10 - uy * 5, apy - uy * 10 + ux * 5);
          ctx.lineTo(apx - ux * 10 + uy * 5, apy - uy * 10 - ux * 5);
          ctx.closePath();
          ctx.fillStyle = cl; ctx.globalAlpha = 0.8; ctx.fill(); ctx.globalAlpha = 1;
        }
      }

      // 이름
      ctx.font = "600 14px var(--font-sans, sans-serif)";
      ctx.textAlign = "center";
      ctx.fillStyle = "#fff";
      ctx.fillText(d.n, px, py - 20);
    }
  }, [data, investor, level, period, sel, wrapW]);

  useEffect(() => { draw(); }, [draw]);

  // 웹폰트(Pretendard) 로드 후 재그리기 — 라벨 폭 측정·클램프 정확도 보장
  useEffect(() => {
    if (typeof document !== "undefined" && document.fonts?.ready) {
      document.fonts.ready.then(() => draw());
    }
  }, [draw]);

  /* ── 인터랙션 ────────────────────────────────── */
  const findHit = (mx: number, my: number): number => {
    const st = stateRef.current;
    if (!st) return -1;
    let best = -1, md = 40;
    st.data.forEach((d, i) => {
      const l = d.t[d.t.length - 1];
      const dist = Math.hypot(mx - st.sx(l[0]), my - st.sy(l[1]));
      if (dist < md) { md = dist; best = i; }
    });
    return best;
  };

  const getQuadrant = (x: number, y: number) =>
    x >= 0 ? (y >= 0 ? "적극 매집" : "매집 둔화") : (y >= 0 ? "관심 전환" : "적극 이탈");

  const handleInteract = (mx: number, my: number) => {
    const hit = findHit(mx, my);
    if (hit === sel) {
      setSel(-1);
      setTip(null);
    } else {
      setSel(hit);
      if (hit >= 0 && stateRef.current) {
        const d = stateRef.current.data[hit];
        const l = d.t[d.t.length - 1];
        setTip({
          show: true,
          x: stateRef.current.sx(l[0]),
          y: stateRef.current.sy(l[1]),
          sector: d,
          quadrant: getQuadrant(l[0], l[1]),
        });
      } else {
        setTip(null);
      }
    }
  };

  const onCanvasClick = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    handleInteract(e.clientX - r.left, e.clientY - r.top);
  };

  const onCanvasTouch = (e: React.TouchEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    const t = e.touches[0];
    const r = e.currentTarget.getBoundingClientRect();
    handleInteract(t.clientX - r.left, t.clientY - r.top);
  };

  const onCanvasMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (sel >= 0) return;
    const r = e.currentTarget.getBoundingClientRect();
    const hit = findHit(e.clientX - r.left, e.clientY - r.top);
    e.currentTarget.style.cursor = hit >= 0 ? "pointer" : "default";
    if (hit >= 0 && stateRef.current) {
      const d = stateRef.current.data[hit];
      const l = d.t[d.t.length - 1];
      setTip({
        show: true,
        x: stateRef.current.sx(l[0]),
        y: stateRef.current.sy(l[1]),
        sector: d,
        quadrant: getQuadrant(l[0], l[1]),
      });
    } else {
      setTip(null);
    }
  };

  if (!data) return null;

  return (
    <div className="mb-6">
      {/* 안내 */}
      <div className="flex items-center gap-3 mb-3 flex-wrap">
        <span className="text-[11px] text-[var(--text-muted)]">
          {INVESTOR_LABELS[investor]} · WICS {level === "large" ? "대분류" : "중분류"} · 클릭하여 궤적 표시
        </span>
      </div>

      {/* 차트 */}
      <div ref={wrapRef} className="relative">
        <canvas
          ref={canvasRef}
          className="w-full rounded-xl"
          style={{ height: chartH, background: "rgba(255,255,255,0.035)", border: "1px solid rgba(255,255,255,0.06)", touchAction: "none" }}
          onClick={onCanvasClick}
          onTouchStart={onCanvasTouch}
          onMouseMove={onCanvasMove}
          onMouseLeave={() => { if (sel < 0) setTip(null); }}
        />
        {tip?.show && (
          <div
            className="absolute pointer-events-none rounded-lg px-3 py-2.5 text-[12px] leading-relaxed border border-white/[0.08] bg-[rgba(12,14,20,0.95)] backdrop-blur-sm"
            style={{
              left: Math.min(tip.x + 16, (wrapW || 600) - 220),
              top: Math.max(0, tip.y - 65),
              opacity: 1,
              transition: "opacity 0.12s",
            }}
          >
            <div className="font-semibold text-[14px] mb-1">{tip.sector.n}</div>
            <span className="text-[var(--text-secondary)]">
              {tip.sector.l} · {tip.quadrant}
            </span>
            <br />
            <span
              className="font-semibold text-[13px]"
              style={{ color: tip.sector.f >= 0 ? "#34b464" : "#e24b4a" }}
            >
              {fmtFlow(tip.sector.f)}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
