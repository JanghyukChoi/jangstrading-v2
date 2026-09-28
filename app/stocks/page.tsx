/* 종목 랭킹 — 서버 컴포넌트 껍데기.

   표 자체는 StocksClient 가 그린다.

   한때 여기에 "수급 상위 종목" 링크 목록을 뒀다가 뺐다 — 이 페이지의 본문이
   이미 랭킹 표라 같은 순위가 화면에 두 번 나왔다. 대신 설명 문단을 둔다.
   목록이 아니라 산문이라 표와 겹치지 않으면서, 클라이언트 렌더인 표 때문에
   비어 있던 HTML 본문을 채운다. 이 페이지가 노리는 검색어가
   "외국인·기관 순매수 상위 종목" 인데 본문이 없으면 뜰 수가 없다.
*/

import Link from "next/link";
import StocksClient from "./StocksClient";
import { fmtAmount, fmtDateKo, loadRankings } from "@/app/lib/seo";

export const dynamic = "force-static";

export default function Page() {
  const { data, date } = loadRankings();
  const rows = data.filter((s) => s.ticker);

  // 오늘 시장 전체의 방향. 표와 겹치지 않는 집계 수치다.
  const sum = (k: "foreign" | "institution" | "corp") =>
    rows.reduce((a, s) => a + (s[k]?.["1m"] ?? 0), 0);
  const buyCount = rows.filter((s) => (s.foreign?.["1m"] ?? 0) > 0).length;

  return (
    <>
      <StocksClient />

      <section className="mt-4">
        <div className="bg-[var(--bg-card)] rounded-2xl p-4 sm:p-6">
          <h2 className="text-[15px] sm:text-[17px] font-semibold text-white mb-1">
            이 표는 무엇인가
          </h2>
          <p className="text-[12px] text-[var(--text-muted)] mb-4">
            {fmtDateKo(date)} 기준 · {rows.length.toLocaleString("ko-KR")}종목
          </p>
          <p className="text-[13px] sm:text-[14px] text-[var(--text-secondary)] leading-[1.8]">
            한국거래소가 공시하는 투자자별 매매동향을 종목별로 정리한 표입니다. 외국인·기관·연기금·기타법인의
            순매수 금액을 1일부터 6개월까지 기간별로 볼 수 있고, 금액이 아니라 시가총액 대비 비중으로
            정렬하면 대형주에 가려진 중소형주의 수급 쏠림이 드러납니다.
          </p>
          <p className="mt-3 text-[13px] sm:text-[14px] text-[var(--text-secondary)] leading-[1.8]">
            최근 1개월 동안 외국인은 전체 {rows.length.toLocaleString("ko-KR")}종목 가운데{" "}
            <strong className="text-white">{buyCount.toLocaleString("ko-KR")}종목</strong>을 순매수했고,
            합계는 <strong className="text-white">{fmtAmount(sum("foreign"))}</strong>입니다. 같은 기간
            기관은 <strong className="text-white">{fmtAmount(sum("institution"))}</strong>,
            기타법인은 <strong className="text-white">{fmtAmount(sum("corp"))}</strong>입니다.
          </p>
          <p className="mt-3 text-[13px] sm:text-[14px] text-[var(--text-secondary)] leading-[1.8]">
            종목을 누르면 누적 순매수 추이와{" "}
            <Link href="/guide/평균단가" className="text-[var(--accent-blue)] hover:underline">
              외국인·기관 추정 평균 매입가
            </Link>
            , 매물대를 얹은 주가 차트를 볼 수 있습니다. 업종별 자금 흐름은{" "}
            <Link href="/sectors" className="text-[var(--accent-blue)] hover:underline">
              섹터
            </Link>
            에서 확인할 수 있습니다.
          </p>
        </div>
      </section>
    </>
  );
}
