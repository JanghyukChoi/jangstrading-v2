import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "AI 시황 분석",
  description: "매일 수급 데이터와 뉴스를 기반으로 자동 생성되는 AI 시황 리포트.",
  alternates: {
    canonical: "https://www.jangstrading.com/reports",
  },
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
