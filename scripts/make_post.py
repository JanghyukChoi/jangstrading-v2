"""
커뮤니티 배포용 글 자동 생성 — docs/posts/<날짜>-<앵글>.md

왜 주 1회인가
  커뮤니티는 같은 사람이 같은 형식으로 매일 올리면 홍보로 보고 차단한다.
  주 1회가 상한선이다. 그래서 기본 실행일을 월요일로 두고, 매주 다른 앵글을
  돌린다. 같은 표를 매번 올리면 그것도 금방 질린다.

앵글 4종 (ISO 주차 % 4)
  avgcost  외국인 평균단가 대비 현재가 괴리
  corp     기타법인 매수 중 '자사주 매입으로 보이는' 패턴 탐지
  breadth  시장 폭 — 몇 종목을 사고 몇 종목을 파는가
  sector   섹터별 자금 이동

숫자는 전부 public/data 에서 읽는다. 지어내는 문장은 없다. 해석 문장은
데이터 조건에 따라 분기할 뿐이다.

실행
  python scripts/make_post.py                # 월요일에만 생성
  python scripts/make_post.py --force        # 요일 무시
  python scripts/make_post.py --angle corp   # 앵글 지정
"""

import argparse
import json
import statistics
import sys
from datetime import date
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "public" / "data"
OUT = BASE / "docs" / "posts"
SITE = "https://www.jangstrading.com"

ANGLES = ["avgcost", "corp", "breadth", "sector"]

# 자사주 매입 판정. 최근 N 영업일 내내 기타법인 순매수이고 일별 편차가 작으면
# 사람이 아니라 프로그램이 사는 것이다. 실측상 SK하이닉스·삼성전자가 변동계수
# 0.03 수준으로 나온다. 일반 수급은 0.5 를 우습게 넘는다.
STEADY_DAYS = 7
STEADY_CV = 0.25


def load(name):
    try:
        return json.loads((DATA / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def won(m):
    """백만원 -> 사람이 읽는 한국어 금액."""
    if m is None:
        return "-"
    a, sign = abs(m), ("+" if m > 0 else "-" if m < 0 else "")
    if a >= 1_000_000:
        return f"{sign}{a/1_000_000:.1f}조"
    if a >= 100:
        return f"{sign}{a/100:,.0f}억"
    return f"{sign}{a:,.0f}백만"


def num(v):
    return f"{v:,.0f}"


# ── 앵글 ────────────────────────────────────────────────────────────
def angle_avgcost(rk, _snaps, _sig):
    rows = [s for s in rk["data"]
            if s.get("ticker") and (s.get("avg_cost") or {}).get("foreign")
            and (s.get("market_cap") or 0) > 30000]
    if len(rows) < 20:
        return None
    rows.sort(key=lambda s: s["avg_cost"]["foreign"]["pnl_pct"])
    under, over = rows[:8], rows[-8:][::-1]

    def block(items):
        w = max(len(s["name"]) for s in items)
        return "\n".join(
            f"{s['name']:<{w}}  현재 {num(s['avg_cost']['price']):>10}"
            f" / 외인평단 {num(s['avg_cost']['foreign']['avg_cost']):>10}"
            f"  ({s['avg_cost']['foreign']['pnl_pct']:+.1f}%)"
            for s in items)

    # 벌어놓은 쪽에서 외국인이 파는가 — 해석 문장을 데이터로 만든다.
    selling = [s for s in over if (s.get("foreign") or {}).get("1m", 0) < 0]
    note = ""
    if len(selling) >= 3:
        worst = min(selling, key=lambda s: s["foreign"]["1m"])
        note = (f"\n눈에 띄는 건, 벌어놓은 {len(over)}종목 중 {len(selling)}종목에서 "
                f"외국인이 최근 1개월 순매도라는 겁니다.\n"
                f"특히 {worst['name']}는 평단 대비 "
                f"{worst['avg_cost']['foreign']['pnl_pct']:+.1f}% 구간에서 "
                f"{won(worst['foreign']['1m'])} 순매도입니다.\n")

    return ("외국인 평균단가 대비 현재가 (시총 3조 이상)", f"""\
회전율 가중 기준가격(Grinblatt & Han, 2005)으로
외국인이 지금 평균 얼마에 들고 있는지 역산해봤습니다.
매일 거래량으로 보유분이 얼마나 교체됐는지를 가중하는 방식입니다.

[외국인이 물려있는 쪽]
{block(under)}

[외국인이 벌어놓은 쪽]
{block(over)}
{note}
추정치입니다. 외국인 전체를 한 명으로 보고 공시된 일별 순매수를
회전율로 가중한 값이라 실제 개별 펀드 단가와는 다릅니다.
방향성 참고용으로만 보시면 됩니다.
""")


def angle_corp(rk, snaps, _sig):
    """최근 며칠간 기타법인이 '기계적으로' 사고 있는 종목을 찾는다."""
    if len(snaps) < STEADY_DAYS:
        return None
    names = {s["ticker"]: s["name"] for s in rk["data"] if s.get("ticker")}

    series = {}
    for snap in snaps[-STEADY_DAYS:]:
        for t, v in (snap.get("corp_1d") or {}).items():
            series.setdefault(t, []).append(v)

    found = []
    for t, vs in series.items():
        if len(vs) < STEADY_DAYS or min(vs) <= 0:
            continue                      # 하루라도 순매도면 프로그램이 아니다
        m = statistics.mean(vs)
        if m < 1000:                      # 10억 미만은 노이즈
            continue
        cv = statistics.pstdev(vs) / m
        if cv <= STEADY_CV:
            found.append((t, m, cv, sum(vs)))
    if not found:
        return None
    found.sort(key=lambda x: -x[1])

    w = max(len(names.get(t, t)) for t, *_ in found[:10])
    table = "\n".join(
        f"{names.get(t,t):<{w}}  하루 평균 {won(m):>8}  편차 {cv*100:.1f}%  "
        f"{STEADY_DAYS}일 합계 {won(tot)}"
        for t, m, cv, tot in found[:10])

    top_t, top_m, _, _ = found[0]
    top_row = next((s for s in rk["data"] if s.get("ticker") == top_t), {})
    f1m = (top_row.get("foreign") or {}).get("1m")
    cross = ""
    if f1m is not None and f1m < 0:
        cross = (f"\n{names.get(top_t,top_t)}는 같은 기간 외국인이 "
                 f"{won(f1m)} 순매도입니다.\n"
                 f"외국인이 파는 물량을 회사가 받고 있는 구조입니다.\n"
                 f'"외국인 대량 순매도"만 보면 악재로 읽히는데,\n'
                 f"받아주는 주체가 회사 자신이면 해석이 달라집니다.\n")

    return ("기타법인 수급으로 자사주 매입 찾기", f"""\
투자자별 매매동향에서 보통 기타법인은 그냥 넘기는데,
여기가 KRX 분류에서 내부자에 가장 가까운 매수 주체입니다.
자사주 매입, 계열사 지분 취득, M&A 목적 장내매집이 전부 여기 잡힙니다.

자사주 매입은 수급 모양이 다릅니다. 사람이 사면 날마다 몇 배씩 튀는데
프로그램이 사면 매일 거의 같은 금액이 찍힙니다.
최근 {STEADY_DAYS}영업일 내내 기타법인 순매수이면서
일별 편차가 {int(STEADY_CV*100)}% 이내인 종목을 뽑아봤습니다.

{table}
{cross}
주의: 기타법인에는 자사주 말고 일반법인 거래도 섞입니다.
실제 자사주 매입인지는 DART 공시를 봐야 확정됩니다.
여기서는 "볼 곳을 찾는" 용도입니다.
""")


def angle_breadth(rk, _snaps, sig):
    a = (sig or {}).get("activity") or {}
    t = (sig or {}).get("trend") or {}
    if not a:
        return None
    fb, fs = a.get("foreign_buy_breadth", 0), a.get("foreign_sell_breadth", 0)
    ib, isl = a.get("inst_buy_breadth", 0), a.get("inst_sell_breadth", 0)
    total = len([s for s in rk["data"] if s.get("ticker")])

    def streak(d):
        n = d.get("foreign_streak_days", 0)
        return (f"{abs(n)}일 연속 " + ("순매수" if n > 0 else "순매도")) if n else "중립"

    read = ("외국인이 지수는 안 건드리면서 종목을 솎아내는 국면입니다."
            if fs > fb * 1.5 else
            "외국인 매수가 넓게 퍼져 있습니다." if fb > fs else
            "외국인 매수·매도가 비슷하게 갈립니다.")

    return ("오늘 시장 폭 — 몇 종목을 사고 몇 종목을 팔았나", f"""\
지수만 보면 안 보이는 게 있어서 종목 수로 세봤습니다.
전체 {total:,}종목 기준입니다.

외국인  순매수 {fb:,}종목 / 순매도 {fs:,}종목
기관    순매수 {ib:,}종목 / 순매도 {isl:,}종목

52주 신고가 {a.get('high_52w',0)}종목 / 신저가 {a.get('low_52w',0)}종목

KOSPI  외국인 {streak(t.get('kospi',{}))}
KOSDAQ 외국인 {streak(t.get('kosdaq',{}))}

{read}
{(sig or {}).get('verdict','')}
""")


def angle_sector(rk, _snaps, _sig):
    agg = {}
    for s in rk["data"]:
        k = s.get("sector_mid")
        if not k or k == "기타":
            continue
        f = (s.get("foreign") or {}).get("1m") or 0
        i = (s.get("institution") or {}).get("1m") or 0
        d = agg.setdefault(k, [0, 0, 0])
        d[0] += f
        d[1] += i
        d[2] += 1
    rows = [(k, f, i, n) for k, (f, i, n) in agg.items() if n >= 3]
    if len(rows) < 10:
        return None
    rows.sort(key=lambda r: -(r[1] + r[2]))
    top, bot = rows[:8], rows[-8:][::-1]

    def block(items):
        w = max(len(k) for k, *_ in items)
        # 합계를 맨 앞에 둔다. 정렬 기준이 합계인데 외국인 열이 먼저 오면
        # "들어온 쪽"에 마이너스가 보여서 읽는 사람이 헷갈린다.
        return "\n".join(
            f"{k:<{w}}  합계 {won(f+i):>8}   (외국인 {won(f)} / 기관 {won(i)}, {n}종목)"
            for k, f, i, n in items)

    return ("최근 1개월 섹터별 자금 이동", f"""\
종목 단위로 보면 잘 안 보여서 업종(WICS 중분류)으로 묶어봤습니다.
외국인+기관 순매수 금액 합산 기준, 최근 1개월입니다.
합계 기준으로 정렬했으니 외국인과 기관이 서로 반대인 업종도 섞여 있습니다.

[자금이 들어온 쪽]
{block(top)}

[자금이 빠진 쪽]
{block(bot)}

종목 3개 미만 업종은 뺐습니다. 대형주 한 종목이 업종 전체를
대표해버리는 걸 막기 위한 것입니다.
""")


HANDLERS = {"avgcost": angle_avgcost, "corp": angle_corp,
            "breadth": angle_breadth, "sector": angle_sector}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--angle", choices=ANGLES)
    ap.add_argument("--force", action="store_true", help="월요일이 아니어도 생성")
    args = ap.parse_args()

    today = date.today()
    if not args.force and not args.angle and today.weekday() != 0:
        print(f"{today} 는 월요일이 아닙니다. 건너뜁니다 (--force 로 무시).")
        return 0

    rk = load("stock-rankings.json")
    if not rk or not rk.get("data"):
        print("stock-rankings.json 을 읽을 수 없습니다.")
        return 1
    sig = load("market-signals.json")

    snaps = []
    for p in sorted((DATA / "snapshots").glob("2*.json"))[-STEADY_DAYS:]:
        try:
            snaps.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass

    angle = args.angle or ANGLES[today.isocalendar().week % len(ANGLES)]
    built = HANDLERS[angle](rk, snaps, sig)
    if not built:
        print(f"앵글 '{angle}' 은 오늘 데이터로 만들 수 없습니다.")
        return 1
    title, body = built

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{rk['date']}-{angle}.md"
    path.write_text(f"""\
# {title}

> 자동 생성 · 기준일 {rk['date']} · 앵글 `{angle}`
>
> **올리기 전에:** 첫 글에는 링크를 넣지 마세요. 정보성 글 2~3개로
> 평판을 만든 뒤에 붙입니다. 하루에 한 커뮤니티만. 주 1회가 상한입니다.
> 자세한 규칙은 [../community-posts.md](../community-posts.md).

## 제목 후보

- {title}
- {body.strip().splitlines()[0]}

## 본문 (여기부터 복사)

```
{body.rstrip()}
```

## 링크를 붙일 때 (평판이 생긴 뒤에만)

```
전체 종목: {SITE}/stocks
계산 방식: {SITE}/guide/평균단가
```
""", encoding="utf-8")
    print(f"생성: {path.relative_to(BASE)}  (앵글 {angle}, {len(body)}자)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
