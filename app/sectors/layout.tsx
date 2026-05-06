import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "섹터별 수급 현황",
  description: "WICS 산업분류 기준 섹터별 외국인·기관 순매수 현황. 대분류·중분류·테마별 수급 흐름을 분석합니다.",
  alternates: {
    canonical: "https://www.jangstrading.com/sectors",
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
