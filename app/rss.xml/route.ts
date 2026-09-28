/* RSS 피드 — /rss.xml

   왜 필요한가: 네이버 서치어드바이저에 "RSS 제출" 메뉴가 있는데 우리는 낼 게
   없었다. 네이버는 사이트맵보다 RSS 를 더 자주 확인한다 — 사이트맵은 "이런
   URL 들이 있다"이고 RSS 는 "새 글이 나왔다"라서 신선도 신호로 쓰인다.

   실을 것은 AI 시황 리포트다. 이 사이트에서 유일하게 '글'인 자산이고 매
   영업일 새로 생긴다. 종목 페이지는 숫자표라 RSS 에 맞지 않는다.

   Route Handler 는 기본적으로 캐시되지 않는다. force-static 으로 빌드 시점에
   한 번 만들고 배포마다 갱신한다 — 데이터가 바뀌면 어차피 재배포된다.
*/

import { loadReportIndex, loadReport } from "@/app/lib/reports";
import { BASE_URL, SITE_NAME } from "@/app/lib/seo";

export const dynamic = "force-static";

/* 네이버 도움말이 "본문 전체를 제공하는 것을 권장"하면서 동시에 "피드 크기에
   따라 제출이 제한될 수 있으니 중요한 콘텐츠만"이라고 한다. 둘을 맞춘다.

   전문을 실으면 한글 UTF-8 이라 1편이 약 6KB 다. 30편 + content:encoded
   중복까지 넣었더니 356KB 가 나왔다. 중복을 없애고 20편으로 줄여 약 120KB.
   더 오래된 리포트는 사이트맵이 이미 덮는다 — 피드는 신선도 신호가 역할이다. */
const MAX_ITEMS = 20;

/** XML 에 넣을 수 없는 문자를 이스케이프한다. 리포트 본문은 Gemini 가 쓴
    자유 텍스트라 &, <, > 가 언제든 들어올 수 있다. */
function xml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** "2026-09-23" -> RFC 822. RSS 규격은 이 형식만 받는다.
    장 마감 후 생성되므로 KST 18:00 로 둔다(= UTC 09:00). */
function rfc822(date: string): string {
  return new Date(`${date}T09:00:00.000Z`).toUTCString();
}

/** CDATA 안에 넣을 문자열. 본문에 "]]>" 가 있으면 섹션이 거기서 끊겨
    XML 이 깨진다. Gemini 가 쓰는 자유 텍스트라 막아 둔다. */
function cdata(s: string): string {
  return `<![CDATA[${s.replace(/\]\]>/g, "]]]]><![CDATA[>")}]]>`;
}

/** 리포트 본문(플레인 텍스트)을 RSS 리더가 읽을 HTML 로 바꾼다.

    본문 형식은 generate_report.py 가 정한다.
      [섹션 제목]   대괄호 한 줄
      - 항목        불릿
      그 외          문단 */
function bodyHtml(body: string): string {
  const esc = (s: string) =>
    s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  const out: string[] = [];
  let bullets: string[] = [];

  const flush = () => {
    if (bullets.length) {
      out.push(`<ul>${bullets.map((b) => `<li>${esc(b)}</li>`).join("")}</ul>`);
      bullets = [];
    }
  };

  for (const raw of body.split("\n")) {
    const line = raw.trim();
    if (!line) {
      flush();
      continue;
    }
    const head = /^\[([^\]]+)\]$/.exec(line);
    if (head) {
      flush();
      out.push(`<h2>${esc(head[1])}</h2>`);
    } else if (/^[-*]\s+/.test(line)) {
      bullets.push(line.replace(/^[-*]\s+/, ""));
    } else {
      flush();
      out.push(`<p>${esc(line)}</p>`);
    }
  }
  flush();
  return out.join("");
}

export async function GET() {
  const index = loadReportIndex().slice(0, MAX_ITEMS);

  const items = index.map((r) => {
    const full = loadReport(r.date);
    const link = `${BASE_URL}/reports/${r.date}`;
    // 네이버는 본문 전체를 권장한다. HTML 로 바꿔 전문을 싣는다.
    const html = full ? bodyHtml(full.body) : "";
    return [
      "<item>",
      `<title>${xml(r.title)}</title>`,
      `<link>${link}</link>`,
      // guid 가 항목의 동일성 판단 기준이다. 링크와 같게 두고 isPermaLink 를
      // 명시한다 — 생략하면 리더마다 다르게 해석한다.
      `<guid isPermaLink="true">${link}</guid>`,
      `<pubDate>${rfc822(r.date)}</pubDate>`,
      `<dc:creator>${SITE_NAME}</dc:creator>`,
      // 전문을 description 에 싣는다. content:encoded 에 같은 걸 또 넣으면
      // 피드 크기가 두 배가 되는데, 네이버가 읽는 건 description 이다.
      `<description>${cdata(html)}</description>`,
      `<category>수급분석</category>`,
      "</item>",
    ].join("");
  });

  const latest = index[0]?.date;

  const body =
    '<?xml version="1.0" encoding="UTF-8"?>' +
    '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"' +
    ' xmlns:dc="http://purl.org/dc/elements/1.1/">' +
    "<channel>" +
    `<title>${SITE_NAME} — 외국인·기관 수급 시황</title>` +
    `<link>${BASE_URL}</link>` +
    "<description>한국거래소 공시 기반 투자자별 매매동향을 매 영업일 정리합니다. " +
    "외국인·기관·연기금·기타법인의 종목별 순매수와 추정 평균 매입가.</description>" +
    "<language>ko</language>" +
    `<atom:link href="${BASE_URL}/rss.xml" rel="self" type="application/rss+xml"/>` +
    (latest ? `<lastBuildDate>${rfc822(latest)}</lastBuildDate>` : "") +
    items.join("") +
    "</channel></rss>";

  return new Response(body, {
    headers: {
      "Content-Type": "application/rss+xml; charset=utf-8",
      "Cache-Control": "public, max-age=3600",
    },
  });
}
