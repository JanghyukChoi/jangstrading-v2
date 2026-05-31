import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "종목 스크리너",
  description: "외국인·기관·연기금 순매수, 가격 모멘텀, PER 등 조건을 직접 설정해 종목을 발굴하세요. KRX 공시 데이터 기반.",
  alternates: {
    canonical: "https://www.jangstrading.com/screener",
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
