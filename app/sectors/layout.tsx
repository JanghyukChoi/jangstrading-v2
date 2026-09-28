import fs from "fs";
import path from "path";
import type { Metadata } from "next";
import Link from "next/link";
import {
  BASE_URL, breadcrumb, fmtAmount, fmtDateKo, jsonLdScript, loadRankings,
} from "@/app/lib/seo";

export const metadata: Metadata = {
  title: "업종·테마별 외국인·기관 순매수 현황",
  description:
    "WICS 산업분류 기준 섹터별 외국인·기관 순매수 현황. 대분류·중분류·테마별 수급 흐름을 분석합니다.",
  alternates: { canonical: `${BASE_URL}/sectors` },
};

/** 대분류 섹터 이름 + 소속 종목 수. 중분류 표에는 안 나오는 축이다. */
function largeSectors() {
  const { data } = loadRankings();
  const agg = new Map<string, number>();
  for (const s of data) {
    if (!s.sector || s.sector === "기타") continue;
    agg.set(s.sector, (agg.get(s.sector) ?? 0) + 1);
  }
  return [...agg.entries()].map(([name, n]) => ({ name, n })).sort((a, b) => b.n - a.n);
}

/* 테마 264개.

   여기가 검색 관점에서 제일 아까운 자산이었다. "원전 관련주", "2차전지
   관련주" 같은 검색어가 붙는 페이지인데 /sectors 에서 264개 중 2개만
   링크돼 있었다 — 나머지 262개는 사이트맵에만 있는 고아 페이지였다. */
function themeRows() {
  let map: Record<string, string[]> = {};
  try {
    const p = path.join(process.cwd(), "public", "data", "theme-map.json");
    map = JSON.parse(fs.readFileSync(p, "utf-8"));
  } catch {
    return [];
  }
  const { data } = loadRankings();
  const byTicker = new Map(data.filter((s) => s.ticker).map((s) => [s.ticker!, s]));
  return Object.entries(map)
    .map(([name, tickers]) => {
      let flow = 0;
      for (const t of tickers) {
        const s = byTicker.get(t);
        if (s) flow += (s.foreign?.["1m"] ?? 0) + (s.institution?.["1m"] ?? 0);
      }
      return { name, n: tickers.length, flow };
    })
    // 자금이 많이 오간 테마가 앞에 오도록. 링크 순서도 중요도 신호다.
    .sort((a, b) => Math.abs(b.flow) - Math.abs(a.flow));
}

/** 중분류 섹터별 1개월 수급 합계. */
function sectorTotals() {
  const { data, date } = loadRankings();
  const agg = new Map<string, { n: number; foreign: number; inst: number }>();
  for (const s of data) {
    const key = s.sector_mid;
    if (!key || key === "기타") continue;
    const cur = agg.get(key) ?? { n: 0, foreign: 0, inst: 0 };
    cur.n += 1;
    cur.foreign += s.foreign?.["1m"] ?? 0;
    cur.inst += s.institution?.["1m"] ?? 0;
    agg.set(key, cur);
  }
  return {
    date,
    rows: [...agg.entries()]
      .map(([name, v]) => ({ name, ...v }))
      .sort((a, b) => b.foreign + b.inst - (a.foreign + a.inst)),
  };
}

export default function Layout({ children }: { children: React.ReactNode }) {
  const { rows, date } = sectorTotals();
  const large = largeSectors();
  const themes = themeRows();
  const crumbs = breadcrumb([
    { name: "홈", url: "/" },
    { name: "섹터", url: "/sectors" },
  ]);

  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: jsonLdScript(crumbs) }} />
      {children}

      {/* 섹터 상세 295개로 가는 서버 렌더 링크 + 크롤 가능한 수치 표.
          클라이언트가 그리는 위 차트만으로는 크롤러가 섹터 페이지를 못 찾는다. */}
      {rows.length > 0 && (
        <section className="mt-4">
          <div className="bg-[var(--bg-card)] rounded-2xl p-5 sm:p-6">
            <h2 className="text-[15px] sm:text-[17px] font-semibold text-white mb-1">
              중분류 섹터별 1개월 수급
            </h2>
            <p className="text-[12px] text-[var(--text-muted)] mb-4">
              {fmtDateKo(date)} 기준 · 외국인+기관 합계 순
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-[12px] sm:text-[13px]">
                <caption className="sr-only">중분류 섹터별 외국인·기관 1개월 순매수</caption>
                <thead>
                  <tr className="text-[var(--text-muted)] border-b border-white/[0.06]">
                    <th scope="col" className="text-left py-2 font-normal">섹터</th>
                    <th scope="col" className="text-right py-2 font-normal">종목</th>
                    <th scope="col" className="text-right py-2 font-normal">외국인</th>
                    <th scope="col" className="text-right py-2 font-normal">기관</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.name} className="border-t border-white/[0.03]">
                      <th scope="row" className="text-left py-2 font-normal">
                        <Link
                          href={`/sectors/${encodeURIComponent(r.name)}`}
                          className="text-[var(--text-secondary)] hover:text-[var(--accent-blue)] transition"
                        >
                          {r.name}
                        </Link>
                      </th>
                      <td className="text-right py-2 num text-[var(--text-muted)]">{r.n}</td>
                      <td className="text-right py-2 num text-[var(--text-secondary)]">{fmtAmount(r.foreign)}</td>
                      <td className="text-right py-2 num text-[var(--text-secondary)]">{fmtAmount(r.inst)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      )}

      {/* 대분류·테마로 가는 링크. 표로 만들면 화면이 무거워지므로 칩으로 깐다.
          크롤러에게는 <a> 목록이고 사람에게는 훑어보는 목록이다. */}
      {(large.length > 0 || themes.length > 0) && (
        <section className="mt-4">
          <div className="bg-[var(--bg-card)] rounded-2xl p-5 sm:p-6 space-y-6">
            {large.length > 0 && (
              <div>
                <h2 className="text-[15px] sm:text-[17px] font-semibold text-white mb-1">
                  대분류 섹터
                </h2>
                <p className="text-[12px] text-[var(--text-muted)] mb-3">
                  WICS 산업분류 기준
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {large.map((s) => (
                    <Link
                      key={s.name}
                      href={`/sectors/${encodeURIComponent(s.name)}`}
                      className="px-2.5 py-1.5 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] text-[12px] sm:text-[13px] text-[var(--text-secondary)] hover:text-white transition"
                    >
                      {s.name}
                      <span className="ml-1.5 num text-[var(--text-muted)]">{s.n}</span>
                    </Link>
                  ))}
                </div>
              </div>
            )}

            {themes.length > 0 && (
              <div>
                <h2 className="text-[15px] sm:text-[17px] font-semibold text-white mb-1">
                  테마별 관련주
                </h2>
                <p className="text-[12px] text-[var(--text-muted)] mb-3">
                  {themes.length}개 테마 · 최근 1개월 자금 유출입이 큰 순서
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {themes.map((t) => (
                    <Link
                      key={t.name}
                      href={`/sectors/${encodeURIComponent(t.name)}`}
                      className="px-2.5 py-1.5 rounded-lg bg-white/[0.04] hover:bg-white/[0.08] text-[12px] sm:text-[13px] text-[var(--text-secondary)] hover:text-white transition"
                    >
                      {t.name}
                      <span className="ml-1.5 num text-[var(--text-muted)]">{t.n}</span>
                    </Link>
                  ))}
                </div>
              </div>
            )}
          </div>
        </section>
      )}
    </>
  );
}
