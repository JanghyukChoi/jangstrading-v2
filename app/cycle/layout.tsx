import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "시장 사이클 분석",
  description: "HMM 머신러닝으로 식별한 4개 시장 국면(Bull/Quiet/Transition/Crisis)과 각 국면별 역사적 우세 섹터 통계. 10년 데이터 walk-forward 검증.",
  alternates: {
    canonical: "https://www.jangstrading.com/cycle",
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
