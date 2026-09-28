/* 텔레그램 구독 유도.

   왜 필요한가: 채널은 매 영업일 발송되고 있는데 사이트에서 들어오는 경로가
   헤더의 라벨 없는 16px 아이콘뿐이었다. 검색으로 들어온 사람이 한 번 보고
   끝나면 재방문이 없다 — 재방문이 없으면 트래픽은 검색 노출에만 묶인다.

   두 가지 크기로 쓴다.
     variant="card" — 홈 하단. 한 번만, 눈에 보이게.
     variant="line" — 종목 상세 2,600 페이지. 한 줄. 여기는 검색 유입의
                      착지점이라 있어야 하지만, 카드를 넣으면 조잡해진다.
*/

const HREF = "https://t.me/jangstrading";

function Icon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" className="shrink-0">
      <path d="M11.944 0A12 12 0 0 0 0 12a12 12 0 0 0 12 12 12 12 0 0 0 12-12A12 12 0 0 0 12 0a12 12 0 0 0-.056 0zm4.962 7.224c.1-.002.321.023.465.14a.506.506 0 0 1 .171.325c.016.093.036.306.02.472-.18 1.898-.962 6.502-1.36 8.627-.168.9-.499 1.201-.82 1.23-.696.065-1.225-.46-1.9-.902-1.056-.693-1.653-1.124-2.678-1.8-1.185-.78-.417-1.21.258-1.91.177-.184 3.247-2.977 3.307-3.23.007-.032.014-.15-.056-.212s-.174-.041-.249-.024c-.106.024-1.793 1.14-5.061 3.345-.48.33-.913.49-1.302.48-.428-.008-1.252-.241-1.865-.44-.752-.245-1.349-.374-1.297-.789.027-.216.325-.437.893-.663 3.498-1.524 5.83-2.529 6.998-3.014 3.332-1.386 4.025-1.627 4.476-1.635z" />
    </svg>
  );
}

export default function TelegramCTA({
  variant = "card",
  label,
}: {
  variant?: "card" | "line";
  label?: string;
}) {
  if (variant === "line") {
    return (
      <a
        href={HREF}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1.5 text-[12px] sm:text-[13px] text-[#29B6F6] hover:underline"
      >
        <Icon size={13} />
        {label ?? "매일 수급 요약 텔레그램으로 받기"}
      </a>
    );
  }

  return (
    <div className="bg-[var(--bg-card)] rounded-2xl p-5 sm:p-6">
      <div className="flex flex-col sm:flex-row sm:items-center gap-4 sm:gap-6">
        <div className="min-w-0 flex-1">
          <h2 className="text-[15px] sm:text-[17px] font-semibold text-white flex items-center gap-2">
            <span className="text-[#29B6F6]">
              <Icon size={17} />
            </span>
            매일 장 마감 후 수급 요약
          </h2>
          <p className="text-[13px] sm:text-[14px] text-[var(--text-secondary)] leading-relaxed mt-1.5">
            외국인·기관이 그날 어디로 갔는지, 연속 매수 종목이 무엇인지
            텔레그램으로 보내드립니다. 무료이고 광고는 없습니다.
          </p>
        </div>
        <a
          href={HREF}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-xl bg-[#29B6F6] text-[#0b1418] text-[14px] font-semibold hover:brightness-110 transition shrink-0"
        >
          <Icon size={15} />
          채널 구독
        </a>
      </div>
    </div>
  );
}
