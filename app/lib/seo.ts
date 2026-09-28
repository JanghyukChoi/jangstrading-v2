/* 서버 전용 SEO 헬퍼.

   이 파일은 서버 컴포넌트에서만 import 한다 — fs 를 쓰기 때문에 클라이언트
   번들에 들어가면 빌드가 깨진다.

   왜 필요한가: 사이트의 모든 페이지가 "use client" 라서 HTML 본문이 290자뿐이었고
   (헤더·푸터·면책문구), 종목 상세 2,600 페이지가 전부 같은 <title> 을 달고 있었다.
   구글 눈에는 2,600개 중복 페이지다. 여기서 만든 메타데이터·구조화데이터·요약
   텍스트가 그 구멍을 메운다.
*/

import fs from "fs";
import path from "path";

export const BASE_URL = "https://www.jangstrading.com";
export const SITE_NAME = "JangsTrading";

export interface StockRow {
  ticker?: string;
  name: string;
  market: string;
  per?: number | null;
  pbr?: number | null;
  market_cap?: number | null;
  sector?: string;
  sector_mid?: string;
  foreign: Record<string, number>;
  institution: Record<string, number>;
  combined: Record<string, number>;
  pension?: Record<string, number>;
  corp?: Record<string, number>;
  price_change?: Record<string, number>;
  avg_cost?: {
    price: number;
    foreign?: { avg_cost: number; pnl_pct: number };
    institution?: { avg_cost: number; pnl_pct: number };
  };
}

interface Rankings {
  date: string;
  data: StockRow[];
}

/* 빌드/요청마다 파일을 다시 읽지 않도록 모듈 스코프에 캐시한다.
   2,600 종목 × 여러 페이지를 렌더할 때 같은 3MB 파일을 반복해서 파싱하면
   빌드가 눈에 띄게 느려진다. */
let cache: Rankings | null = null;

export function loadRankings(): Rankings {
  if (cache) return cache;
  try {
    const p = path.join(process.cwd(), "public", "data", "stock-rankings.json");
    cache = JSON.parse(fs.readFileSync(p, "utf-8")) as Rankings;
  } catch {
    cache = { date: "", data: [] };
  }
  return cache;
}

export function findStock(ticker: string): StockRow | null {
  return loadRankings().data.find((s) => s.ticker === ticker) ?? null;
}

/* URL 세그먼트를 원래 이름으로 되돌린다.

   왜 한 번 디코딩으로 안 되는가: generateStaticParams 가 encodeURIComponent
   한 값을 돌려주는데 Next 가 라우트를 만들 때 **한 번 더** 인코딩한다.
   그래서 컴포넌트가 받는 params 는 이중 인코딩이다.

     실제 이름            건강관리
     params.name         %25EA%25B1%25B4%25EA%25B0%2595...
     decodeURIComponent  %EA%B1%B4%EA%B0%95...      <- 여기서 멈췄다

   그 결과 /sectors 상세 295 페이지가 h1 에 퍼센트 문자열을 찍고 소속 종목을
   0개로 계산했다. generateMetadata 는 받는 값이 달라서 제목만 멀쩡했다.

   요청 시점(dynamicParams) 방문은 단일 인코딩으로 들어오므로, 횟수를 가정하지
   않고 **변하지 않을 때까지** 푼다. 잘못된 퍼센트 시퀀스면 그대로 돌려준다.
   테마명에 '/' 가 든 것("전후 재건(우크라/중동 전쟁 등)")도 이 경로로 복원된다. */
export function decodeSegment(raw: string): string {
  let v = raw;
  for (let i = 0; i < 4; i++) {
    let next: string;
    try {
      next = decodeURIComponent(v);
    } catch {
      return v;           // 이름에 들어간 진짜 '%' — 더 풀면 안 된다
    }
    if (next === v) return v;
    v = next;
  }
  return v;
}

/* 종목 상세에서 이어 줄 이웃 종목.

   왜: 종목 페이지끼리 서로 링크가 하나도 없었다. 섹터 페이지를 고치고 나서도
   우선주 132개는 sector 가 "기타" 라 어떤 섹터 페이지에도 안 잡혀 고아로
   남는다. 보통주에서 우선주로 잇는 링크가 그걸 메우고, 동시에 "삼성전자를
   보다가 삼성전자우로" 라는 실제 이동 경로이기도 하다.

   형제 판정은 종목코드 앞 5자리로 한다. 한국 종목코드는 발행사 단위로
   배정되어 보통주와 우선주가 앞 5자리를 공유한다.
     005930 삼성전자 / 005935 삼성전자우
     005380 현대차   / 005385 현대차우 / 005387 현대차2우B
     006800 미래에셋증권 / 00680K 미래에셋증권2우B
   이름 앞글자로 묶으면 "한화" 가 한화오션·한화솔루션을 잘못 끌어온다. */
export function relatedStocks(ticker: string, limit = 8) {
  const { data } = loadRankings();
  const self = data.find((s) => s.ticker === ticker);
  if (!self) return { siblings: [], peers: [] };

  const stem = ticker.slice(0, 5);
  const siblings = data.filter(
    (s) => s.ticker && s.ticker !== ticker && s.ticker.slice(0, 5) === stem
  );

  const key = self.sector_mid && self.sector_mid !== "기타" ? self.sector_mid : self.sector;
  const sibSet = new Set(siblings.map((s) => s.ticker));
  const peers =
    key && key !== "기타"
      ? data
          .filter(
            (s) =>
              s.ticker &&
              s.ticker !== ticker &&
              !sibSet.has(s.ticker) &&
              (s.sector_mid === key || s.sector === key)
          )
          // 시총 큰 순. 링크 순서도 중요도 신호이고, 사람이 볼 때도 자연스럽다.
          .sort((a, b) => (b.market_cap ?? 0) - (a.market_cap ?? 0))
          .slice(0, limit)
      : [];

  return { siblings, peers, sectorName: key && key !== "기타" ? key : null };
}

/** 백만원 단위 값을 한국어 표기로. 검색 스니펫에 그대로 들어간다. */
export function fmtAmount(millionWon: number | null | undefined): string {
  if (millionWon == null || !Number.isFinite(millionWon)) return "-";
  const won = millionWon * 1_000_000;
  const abs = Math.abs(won);
  const sign = won > 0 ? "+" : won < 0 ? "-" : "";
  if (abs >= 1e12) return `${sign}${(abs / 1e12).toFixed(1)}조원`;
  if (abs >= 1e8) return `${sign}${Math.round(abs / 1e8).toLocaleString("ko-KR")}억원`;
  if (abs >= 1e4) return `${sign}${Math.round(abs / 1e4).toLocaleString("ko-KR")}만원`;
  return `${sign}${Math.round(abs).toLocaleString("ko-KR")}원`;
}

export function fmtPrice(won: number | null | undefined): string {
  if (won == null || !Number.isFinite(won)) return "-";
  return `${Math.round(won).toLocaleString("ko-KR")}원`;
}

export function fmtPct(v: number | null | undefined, digits = 2): string {
  if (v == null || !Number.isFinite(v)) return "-";
  return `${v > 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

/** "2026-09-23" -> "2026년 9월 23일" */
export function fmtDateKo(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return iso;
  return `${m[1]}년 ${Number(m[2])}월 ${Number(m[3])}일`;
}

/* JSON-LD 를 <script> 로 직렬화한다.

   Next 문서 권고대로 '<' 를 < 로 치환한다. 종목명·섹터명이 데이터에서
   오므로 이론적으로 </script> 주입이 가능하다 — 지금 데이터에는 없지만
   방어해 두는 비용이 0 이다. */
export function jsonLdScript(data: unknown): string {
  return JSON.stringify(data).replace(/</g, "\\u003c");
}

/** 홈 > 상위 > 현재 형태의 빵부스러기. 구글 검색결과에 경로로 노출된다. */
export function breadcrumb(items: { name: string; url: string }[]) {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((it, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: it.name,
      item: `${BASE_URL}${it.url}`,
    })),
  };
}
