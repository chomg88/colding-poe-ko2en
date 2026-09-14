#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
POE2 경로석 시세 — 구간표와 수집.

서판과 달리 카탈로그가 없다. 경로석 값은 붙은 옵션이 아니라 **속성**에서 나기 때문이다.
매물의 explicit 은 전부 몬스터 쪽 위험 옵션(몬스터 피해 증가, 저항 최대치 -7% 따위)이고,
사는 사람이 보는 것은 아이템에 찍힌 수치다.

    부활 횟수 0 · 아이템 희귀도 +28% · 무리 규모 +25% · 몬스터 효율 +16% · 경로석 출현 확률 +100%

이 수치들은 stat id 가 아니라 거래소의 map_filters 로 검색한다. 그래서 poe2db 를 긁어
문구를 맞출 일이 없고, 무엇을 물어볼지는 아래 AXES 표가 전부다.

무엇을 알아냈나 (2026-09-14, Forbidden Rites)
────────────────────────────────────────────
14등급 이하는 보지 않는다. 15·16등급만 값이 붙는다.

  등급 바닥          15등급 0.05카오스 · 16등급 1.1카오스
  몬스터 효율 70%+   15등급 9카오스 · 16등급 25카오스   (상한 86)
  몬스터 희귀도 90%+ 15등급 12카오스 · 16등급 22카오스  (상한 ~103)
  아이템 희귀도 75%+ 16등급 20카오스                   (상한 16등급 ~89 · 15등급 ~99)
  무리 규모 45%+     16등급 15카오스                   (상한 16등급 ~54 · 15등급 ~64)
  출현 확률 120%+    16등급 24카오스                   (상한 16등급 ~139 · 15등급 ~179)

15등급이 16등급보다 높게 굴러간다. 그래서 구간을 등급마다 따로 둔다 — 16등급에 '희귀도 90'
구간을 두면 영영 매물 없는 빈 키가 된다.

축 하나가 끝까지 굴렀느냐로 값이 갈린다. 품질 축 넷(효율·몬스터 희귀도·아이템 희귀도·
무리 규모)은 **높은 값에서 서로 안 붙는다** — 15등급 효율70+ & 몬희70+ 가 0건이다(낮은
구간에서는 붙는다. 효율30+ & 몬희30+ 는 3144건). 그래서 조합 키는 두지 않는다. 서판에서
쓴 '가장 비싼 축 하나가 값을 정한다' 가 여기서는 더 잘 맞는다.

금·경험치 축은 필터가 있는데도 매물이 0이다 — 이 리그 경로석에는 안 붙는다. 아이템 수량도
없다(그 자리를 아이템 희귀도가 대신한다).

    python3 tools/waystone_prices.py --list          # 물어볼 키 목록만 본다
    python3 tools/waystone_prices.py --probe 5       # 다섯 키만 실제로 물어본다 (안 올린다)

상시 수집은 서판 수집기가 같이 돈다 — tools/tablet_prices.py 가 이 모듈을 불러 섞어 돈다.
따로 돌리면 거래소 IP 한도를 두 프로세스가 나눠 쓰게 돼 서판 쪽이 그만큼 느려진다.
"""
import argparse, sys, time, urllib.parse

TIERS = (16, 15)

# 축 id → (거래소 map_filters 키, 화면에 쓸 이름, 단위, 등급별 구간)
#
# 구간은 '이 값 이상' 으로 건다. 맨 위 구간은 그 등급의 상한 근처다 — 그보다 위는 매물이
# 0이라 키를 둬도 값이 안 온다. min 필터는 그 속성이 붙은 매물만 고른다(속성이 없는 것은
# 0으로 치지 않고 아예 빠진다).
AXES = {
    "eff":    ("map_magic_monsters", "몬스터 효율",      "%", {16: (30, 50, 70, 86), 15: (30, 50, 70, 86)}),
    "rare":   ("map_rare_monsters",  "몬스터 희귀도",    "%", {16: (30, 50, 70, 90), 15: (30, 50, 70, 90)}),
    "iir":    ("map_iir",            "아이템 희귀도",    "%", {16: (40, 60, 75, 85), 15: (40, 60, 75, 85, 90)}),
    "pack":   ("map_packsize",       "무리 규모",        "%", {16: (25, 35, 45),     15: (25, 35, 45, 55)}),
    "bonus":  ("map_bonus",          "경로석 출현 확률", "%", {16: (100, 110, 120),  15: (100, 120, 140, 160)}),
    "revive": ("map_revives",        "부활 횟수",        "회", {16: (1,),            15: (1,)}),
}


def query(tier, axis=None, band=None):
    """거래소 검색 본문. 등급은 종류(base)로 못 박고 축 하나를 얹는다."""
    q = {"status": {"option": "securable"}, "type": f"경로석 ({tier}등급)"}
    if axis:
        q["filters"] = {"map_filters": {"filters": {AXES[axis][0]: {"min": band}}}}
    return {"query": q, "sort": {"price": "asc"}}


def jobs():
    """물어볼 키 목록. [(키, 등급, 축, 구간)] — 축이 None 이면 그 등급의 바닥값이다."""
    out = [(f"{t}:base", t, None, None) for t in TIERS]
    for t in TIERS:
        for a, (_f, _label, _unit, bands) in AXES.items():
            out += [(f"{t}:{a}:{b:g}", t, a, b) for b in bands[t]]
    return out


def label(tier, axis, band):
    return f"{tier}등급 " + ("등급 바닥" if not axis else
                            f"{AXES[axis][1]} {band:g}{AXES[axis][2]}+")


def look(api, job, rates, sample):
    """키 하나. 값 내는 방식은 서판과 같다 — 싼 매물 열 건의 최저·중앙값."""
    _key, tier, axis, band = job
    return sample(api, query(tier, axis, band), rates)


def compose(league, b, rates, seen):
    """페이지가 읽을 문서. 구간표를 같이 실어 보낸다 — 경로석에는 카탈로그 파일이 없고,
    화면은 이 파일 하나만 받아서 표를 그린다."""
    ats = [v[0] for v in b.values() if v and v[0]]
    return {
        "schema": 1, "league": league, "publishedAt": int(time.time()),
        "updatedAt": max(ats) if ats else 0,
        "rates": {k: v for k, v in rates.items() if k != "exalted"},
        "progress": [seen, len(jobs())], "tiers": list(TIERS),
        "axes": [{"id": a, "label": label, "unit": unit,
                  "bands": {str(t): [float(x) for x in bands[t]] for t in TIERS}}
                 for a, (_f, label, unit, bands) in AXES.items()],
        "b": b,
    }


def main():
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    ap = argparse.ArgumentParser(description="POE2 경로석 시세 — 구간 확인용")
    ap.add_argument("--list", action="store_true", help="물어볼 키 목록만 본다")
    ap.add_argument("--probe", type=int, metavar="N", help="N 개 키를 실제로 물어본다 (올리지 않는다)")
    ap.add_argument("--gap", type=float, default=20, help="키 사이 간격(초, 기본 20)")
    args = ap.parse_args()

    js = jobs()
    if args.list or not args.probe:
        for key, tier, axis, band in js:
            print(f"  {key:<16} {label(tier, axis, band)}")
        print(f"  키 {len(js)}개 · 45초 간격이면 한 바퀴 {len(js) * 45 / 60:.0f}분")
        return

    import tablet_prices as tp
    api = tp.Trade("Forbidden Rites")
    rates = tp.money(api, {"exalted": 1.0})
    print("  환산: " + " · ".join(f"1 {k} = {v} 엑잘" for k, v in rates.items() if k != "exalted"))
    ch = rates.get("chaos") or 1
    for n, job in enumerate(js[:args.probe], 1):
        _key, tier, axis, band = job
        rec = look(api, job, rates, tp.sample)
        med = f"{rec[4] / ch:.1f}카오스" if rec[4] is not None else "매물 없음"
        print(f"  [{n}/{args.probe}] {label(tier, axis, band):<28} 매물 {rec[1]:>6} · 중앙 {med}")
        if n < args.probe:
            time.sleep(args.gap)


if __name__ == "__main__":
    main()
