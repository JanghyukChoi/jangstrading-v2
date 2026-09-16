"""
액면분할·병합 보정. 시계열을 쓰는 쪽은 전부 이걸 거쳐야 한다.

문제: 스냅샷의 prices 는 그날 실제로 찍힌 가격이라 수정주가가 아니다.
삼성전자는 2018-05-04 에 2,650,000 -> 51,900 으로 떨어진다(50:1 분할).
보정 없이 수익률이나 모멘텀을 내면 그날 -98% 다.

  10년 백테스트 데이터: 3,234종목 중 1,095종목(33.8%), 1,842건
  라이브 시계열(329일): 2,884종목 중 201종목(7.0%), 255건
                        최근 1년 내 분할 163종목 -> 60·120일 모멘텀이 깨진다

보정 근거는 **시가총액이 분할 때 연속**이라는 점이다(삼성전자 331조 -> 333조).

    주식수 n_t = 시가총액_t / 주가_t
    가격비 r_p = P_t / P_{t-1},   주식수비 r_n = n_t / n_{t-1}

한국 주식은 일일 가격제한이 ±30% 라 r_p 가 [0.65, 1.40] 밖이면 정상 등락이
아니다. 그때 r_p x r_n 이 다시 범위 안으로 들어오면 주식수 변화가 그 점프를
설명한 것이므로 분할/병합/감자로 보고 과거 가격을 r_n 으로 나눈다.
설명되지 않으면(거래정지 후 재개, 데이터 오류) 그날 수익률을 못 믿는 것으로
표시한다.

시장 규칙에서 나온 자기검증형 규칙이라 손댈 임계값이 없다 — ±30% 는 제도지
튜닝 파라미터가 아니다.

가장 최근 가격은 절대 바뀌지 않는다(계수가 1). 과거만 현재 스케일로 당겨온다.

**보정되지 않는 경우가 남는다.** 무상증자 권리락은 상장주식수가 당일에 안 바뀐다 —
저스템은 2025-12-30 에 15,420 -> 5,810 으로 떨어졌는데 주식수(7,262,750)는
16 거래일 뒤인 2026-01-23 에야 22,573,581 로 갱신됐다. 무상감자·거래재개도 같다.
라이브 329일 기준 255건 중 114건만 당일 판정이 되고 141건이 남는다.

검증 안 되는 배수를 추측해서 갖다 붙이면 틀린 숫자를 만들어낸다. 대신 그 날을
**단절(discontinuity)** 로 표시하고, 그 구간을 지나는 수익률·모멘텀은 계산하지
않는다. 모르는 걸 모른다고 두는 쪽이 맞다.
"""

# 한국 일일 가격제한 ±30%. 양쪽에 여유를 둔다.
LIMIT_LO, LIMIT_HI = 0.65, 1.40


def detect_splits(prices, market_caps):
    """[(인덱스, 배수)] — 그 시점 이전 가격을 나눠야 할 배수."""
    n = min(len(prices), len(market_caps))
    out = []
    for t in range(1, n):
        p0, p1 = prices[t - 1], prices[t]
        m0, m1 = market_caps[t - 1], market_caps[t]
        if not (p0 and p1 and m0 and m1) or p0 <= 0 or p1 <= 0:
            continue
        rp = p1 / p0
        if LIMIT_LO <= rp <= LIMIT_HI:
            continue
        rn = (m1 / p1) / (m0 / p0)          # 주식수비
        if rn > 0 and LIMIT_LO <= rp * rn <= LIMIT_HI:
            out.append((t, rn))
    return out


def adjust(prices, market_caps):
    """분할 보정된 가격 리스트와, 수익률을 믿을 수 있는 날 마스크를 돌려준다.

    Returns: (adjusted_prices, ok) — ok[t] 는 t-1 -> t 수익률의 사용 가능 여부.
    """
    n = len(prices)
    adj = [float(p) if p else 0.0 for p in prices]
    ok = [True] * n
    if n:
        ok[0] = False

    splits = dict(detect_splits(prices, market_caps))
    for t in range(1, n):
        p0, p1 = prices[t - 1], prices[t]
        if not p0 or not p1 or p0 <= 0 or p1 <= 0:
            ok[t] = False
        elif not (LIMIT_LO <= p1 / p0 <= LIMIT_HI) and t not in splits:
            ok[t] = False               # 설명 안 되는 점프 — 수익률을 버린다

    # t 시점 분할은 그 이전 가격을 전부 배수로 나눈다. 뒤에서부터 누적.
    for t0 in sorted(splits, reverse=True):
        k = splits[t0]
        for i in range(t0):
            adj[i] /= k
    return adj, ok


def discontinuities(prices, market_caps):
    """보정 후에도 설명되지 않는 가격 단절의 인덱스 집합.

    이 날을 지나는 수익률·모멘텀은 믿을 수 없다. 무상증자 권리락, 무상감자,
    거래정지 후 재개처럼 상장주식수가 뒤늦게 갱신되는 사건들이다.
    """
    n = len(prices)
    splits = dict(detect_splits(prices, market_caps))
    out = set()
    for t in range(1, n):
        p0, p1 = prices[t - 1], prices[t]
        if not p0 or not p1 or p0 <= 0 or p1 <= 0:
            continue
        if not (LIMIT_LO <= p1 / p0 <= LIMIT_HI) and t not in splits:
            out.add(t)
    return out


def clean_since(row):
    """단절 없이 이어지는 구간의 시작 인덱스.

    시그널이 lookback 일을 볼 때 `len(prices) - clean_since(row) >= lookback`
    이 아니면 그 종목은 건너뛰어야 한다.
    """
    d = discontinuities(row.get("prices") or [], row.get("market_cap") or [])
    return (max(d) if d else 0)


def adjust_in_place(row):
    """timeseries dict({prices, market_cap, ...})의 prices 를 보정한다.

    반환: 보정 건수. market_cap 이 없으면 아무것도 하지 않는다(판정 불가).
    """
    prices = row.get("prices")
    mcaps = row.get("market_cap")
    if not prices or not mcaps:
        return 0
    splits = detect_splits(prices, mcaps)
    if not splits:
        return 0
    adj, _ = adjust(prices, mcaps)
    # 정수 가격을 유지한다. 소수점이 붙으면 화면·비교에서 지저분해진다.
    row["prices"] = [round(x) if x else 0 for x in adj]
    return len(splits)
