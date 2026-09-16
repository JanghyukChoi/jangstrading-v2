import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "종목별 순매수 랭킹",
  description: "외국인·기관·연기금 순매수 종목 랭킹. 기간별 순매수 금액과 시총 대비 비중, 외국인·기관 추정 평균 매입가를 한눈에 확인하세요.",
  alternates: {
    canonical: "https://www.jangstrading.com/stocks",
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
