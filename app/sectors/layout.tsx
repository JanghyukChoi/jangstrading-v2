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
    </>
  );
}
