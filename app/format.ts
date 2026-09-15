/** 화면 표기 공통 규칙. */

/**
 * PER 표기. 적자 기업은 PER 이 음수로 나오는데, 숫자로 보여주면 "싸다"로 읽힌다
 * (SK이노베이션 -6.4 는 6.4배가 아니라 적자라는 뜻이다). 전 종목의 33%(865개)가
 * 여기 해당한다. 0 이하는 배수가 아니라 상태이므로 "적자"로 적는다.
 */
export function perLabel(per?: number | null): string {
  if (per == null) return "-";
  return per > 0 ? per.toFixed(1) : "적자";
}

/** 필터·정렬에 쓸 PER. 적자는 "PER 낮은 순"에 끼면 안 되므로 제외한다. */
export function perValue(per?: number | null): number | null {
  return per != null && per > 0 ? per : null;
}
