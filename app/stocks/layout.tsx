import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "종목별 순매수 랭킹",
  description: "외국인·기관 투자자 순매수 종목 랭킹. 매수전환, 매도전환, 주도주, 단기·장기 수급상위 종목을 한눈에 확인하세요.",
  alternates: {
    canonical: "https://www.jangstrading.com/stocks",
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
