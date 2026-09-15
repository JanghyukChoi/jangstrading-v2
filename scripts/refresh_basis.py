"""
cost-basis.json 의 상태만 가지고 평균단가·매물대를 다시 뽑는다. API 호출 없음.

쓸 일: cost_basis.summarize / _bars 의 표현 방식을 바꿨거나, build_cost_basis.py 로
상태를 새로 만든 뒤. 매일 돌 필요는 없다 — kis_fetch 가 하루치를 갱신하면서
같은 일을 한다.

  python scripts/refresh_basis.py            # 확인만 (파일 안 건드림)
  python scripts/refresh_basis.py --write
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cost_basis as cb  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "public" / "data"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    raw = json.loads((DATA / "cost-basis.json").read_text(encoding="utf-8"))
    state = raw["data"]
    print(f"상태 {len(state)}종목 (기준 {raw.get('updated_through')})")

    # ── 종목 랭킹의 avg_cost ────────────────────────────────────────
    rk_path = DATA / "stock-rankings.json"
    rk = json.loads(rk_path.read_text(encoding="utf-8"))
    changed = dropped = 0
    for s in rk["data"]:
        e = state.get(s["ticker"])
        close = (s.get("avg_cost") or {}).get("price") or 0
        if close <= 0 or not e:
            continue
        out = {"price": close}
        for key, label in (("f", "foreign"), ("i", "institution")):
            r = cb.summarize(e.get(key), close)
            if r:
                out[label] = {"avg_cost": r["reference"], "pnl_pct": r["cgo"]}
        if len(out) > 1:
            if out != s.get("avg_cost"):
                changed += 1
            s["avg_cost"] = out
        elif s.pop("avg_cost", None):
            dropped += 1
    print(f"  stock-rankings.json: {changed}종목 갱신, {dropped}종목 제거")

    # ── 일봉 파일의 매물대 ──────────────────────────────────────────
    touched = 0
    for p in sorted((DATA / "ohlc").glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        if not d.get("c"):
            continue
        e = state.get(d.get("t") or p.stem)
        before = (d.get("fb"), d.get("ib"))
        for key, fld in (("f", "fb"), ("i", "ib")):
            r = cb.summarize(e.get(key), d["c"][-1]) if e else None
            if r and r["basis"]:
                d[fld] = [[b["price"], b["weight"]] for b in r["basis"]]
            else:
                d.pop(fld, None)
        if (d.get("fb"), d.get("ib")) != before:
            touched += 1
            if args.write:
                p.write_text(json.dumps(d, separators=(",", ":")), encoding="utf-8")
    print(f"  ohlc/: {touched}개 파일 변경")

    if args.write:
        rk_path.write_text(json.dumps(rk, ensure_ascii=False, separators=(",", ":")),
                           encoding="utf-8")
        print("저장 완료")
    else:
        print("확인만 함 (--write 로 저장)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
