/* 종목 상세의 변동성 알림.

   **상위 10% 일 때만 나온다.** 나머지 종목에는 아무것도 띄우지 않는다.
   검정에서 살아남은 것이 "상위 10% 가 시장을 밑돈다" 하나뿐이기 때문이다.
   하위 10%(조용한 종목)는 -0.60% / t=-0.72 로 아무 의미가 없었다. 여기에
   "안전합니다" 같은 표시를 붙이면 검정하지 않은 주장을 하는 셈이 된다.

   문구 원칙
     통계 용어를 쓰지 않는다. "4번 중 3번" 으로 쓴다.
     그리고 반대 경우를 같은 문단에 적는다 — 4번 중 1번은 시장을 이겼다.
     그 한 문장이 면책 역할까지 한다. 별도의 "예측이 아닙니다" 문구는
     사용자 요청으로 뺐다(2026-09-29). 사이트 전역 면책은 푸터에 있고,
     한계 전체는 /guide/변동성 에 있다.
*/

import Link from "next/link";

export interface Vol {
  daily: number;      // 하루 평균 변동폭 %
  pct: number | null; // 백분위 (100 = 가장 요동)
  top: boolean;
}

export default function VolatilityNote({ v }: { v: Vol | null }) {
  if (!v || !v.top || v.pct == null) return null;
  const rank = Math.max(1, 101 - v.pct);   // 상위 몇 %인가

  return (
    <section className="mt-4">
      <div className="bg-[var(--bg-card)] rounded-2xl p-5 sm:p-6">
        <div className="flex items-start gap-3">
          <span
            className="mt-0.5 shrink-0 text-[var(--accent-amber)]"
            aria-hidden="true"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 12h3l3 7 4-14 3 7h5" />
            </svg>
          </span>
          <div className="min-w-0">
            <h2 className="text-[15px] sm:text-[17px] font-semibold text-white">
              많이 흔들리는 종목입니다
            </h2>
            <p className="mt-1.5 text-[13px] sm:text-[14px] text-[var(--text-secondary)] leading-relaxed">
              지난 1년간 <strong className="text-white num">하루 평균 ±{v.daily.toFixed(1)}%</strong>{" "}
              움직였습니다. 시가총액 1,000억원 이상 종목 중{" "}
              <strong className="text-white">가장 크게 움직이는 상위 {rank}%</strong>입니다.
            </p>
            <p className="mt-3 text-[13px] sm:text-[14px] text-[var(--text-secondary)] leading-relaxed">
              이 정도로 흔들리는 종목들은 지난 10년간 3개월 뒤에 시장보다 평균{" "}
              <strong className="text-white">4.0% 낮았고</strong>,{" "}
              <strong className="text-white">4번 중 3번</strong> 시장을 따라가지 못했습니다.
              나머지 1번은 시장을 이겼습니다.
            </p>
            <p className="mt-3 text-[12px] sm:text-[13px] text-[var(--text-muted)] leading-relaxed">
              <Link href="/guide/변동성" className="text-[var(--accent-blue)] hover:underline">
                왜 그런가요?
              </Link>
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
