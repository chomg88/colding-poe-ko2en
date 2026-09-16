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
무리 규모)은 **높은 값에서 서로 안 붙는다** — 16등급 효율50+ & 몬희50+ 가 0건이다.

낮은 구간끼리는 붙는다 (2026-09-16 확인)
────────────────────────────────────────
붙는 자리를 전부 세어 보니 품질 축 쌍은 **각 축의 맨 아래 한두 구간에서만** 살아 있었다.
한 칸만 올려도 0으로 떨어진다 — 16등급 효율30+ & 무리25+ 는 112건인데 무리를 35로
올리면 0건이다.

그 살아 있는 자리의 값을 재 보니 둘로 갈렸다.

  효율이 낀 조합은 값이 뛴다     16등급 효율30+ & 몬희50+ 24.5카오스 (효율30 단독 6.4)
                                15등급 효율50+ & 몬희50+ 60카오스   (효율50 단독 9)
  효율이 없는 조합은 제자리다    16등급 몬희30+ & 아희40+ 3카오스   (아희40 단독 3)

그래서 조합 키는 **조합값이 두 축 각각의 단독값보다 뚜렷이 높은 것만** 둔다(아래 COMBOS).
제자리인 조합에 키를 두면 이미 있는 값을 한 번 더 적는 것뿐이고 한 바퀴 슬롯만 먹는다.

출현 확률은 조합에 넣지 않는다. 다른 축과 제일 잘 붙지만(16등급 무리25+ & 출현100+ 가
4303건) 그건 출현 확률이 품질 굴림과 따로 놀기 때문이고, 실제로 쓰이는 것은 130+ 짜리
단독이다.

금·경험치 축은 필터가 있는데도 매물이 0이다 — 이 리그 경로석에는 안 붙는다. 아이템 수량도
없다(그 자리를 아이템 희귀도가 대신한다).

부활 횟수는 뺐다 (2026-09-16). 매물은 많은데 값이 거기서 안 난다 — 올라가 있던 값으로
15등급 부활1+ 의 중앙값이 등급 바닥과 똑같은 4엑잘이었고, 16등급도 바닥의 1.4배(102 대 75)에
그쳤다. 다른 축과 달리 %가 아니라 횟수라 구간도 '1회 이상' 하나뿐이다 — 한 축이 등급마다
한 키씩 슬롯만 먹고 바닥값을 한 번 더 적는 자리였다.

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
}

# 조합 키 — ((축, 구간), (축, 구간)). 위 「낮은 구간끼리는 붙는다」에서 고른 것들이다.
# 기준 둘: 중앙값 4카오스 이상, 그리고 두 축 각각의 단독값보다 1.5배 이상.
# 매물이 마흔 건도 안 되는 자리는 두지 않는다 — 한두 건 팔리면 값이 통째로 흔들린다.
COMBOS = {
    16: (
        (("eff", 50), ("rare", 30)),     # 37.0카오스 · 1.6배 · 87건
        (("eff", 30), ("rare", 50)),     # 24.5      · 3.8배 · 191건
        (("rare", 50), ("iir", 40)),     # 11.0      · 2.6배 · 56건
        (("eff", 30), ("iir", 40)),      # 10.0      · 1.6배 · 162건
    ),
    15: (
        (("eff", 50), ("rare", 50)),     # 60.0카오스 · 6.7배 · 99건
        (("eff", 30), ("iir", 60)),      # 30.0      · 15.0배 · 68건
        (("eff", 50), ("iir", 40)),      # 30.0      · 3.3배 · 93건
        (("eff", 50), ("pack", 25)),     # 21.0      · 2.3배 · 86건
        (("eff", 30), ("rare", 50)),     # 12.0      · 6.0배 · 1158건
        (("rare", 50), ("pack", 35)),    # 11.2      · 3.0배 · 46건
        (("eff", 30), ("pack", 35)),     # 11.0      · 2.9배 · 157건
        (("rare", 30), ("iir", 60)),     # 10.0      · 5.0배 · 265건
        (("iir", 60), ("pack", 25)),     #  9.0      · 4.5배 · 72건
        (("rare", 50), ("iir", 40)),     #  6.4      · 3.2배 · 918건
        (("eff", 30), ("rare", 30)),     #  4.5      · 12.6배 · 4128건
        (("eff", 30), ("iir", 40)),      #  4.0      · 11.2배 · 1951건
    ),
}


def query(tier, parts=()):
    """거래소 검색 본문. 등급은 종류(base)로 못 박고 축을 얹는다.

    parts 는 ((축, 구간), ...) 다. 비면 그 등급의 바닥값이고, 하나면 단독 구간,
    둘이면 조합이다 — map_filters 는 여러 축을 한 묶음에 받아 전부 만족하는 매물만 준다."""
    q = {"status": {"option": "securable"}, "type": f"경로석 ({tier}등급)"}
    if parts:
        q["filters"] = {"map_filters": {
            "filters": {AXES[a][0]: {"min": b} for a, b in parts}}}
    return {"query": q, "sort": {"price": "asc"}}


def key_of(tier, parts):
    """키 이름. 바닥 '16:base' · 단독 '16:eff:50' · 조합 '16:eff50+rare30'."""
    if not parts:
        return f"{tier}:base"
    if len(parts) == 1:
        return f"{tier}:{parts[0][0]}:{parts[0][1]:g}"
    return f"{tier}:" + "+".join(f"{a}{b:g}" for a, b in parts)


def jobs():
    """물어볼 키 목록. [(키, 등급, parts)] — parts 가 비면 그 등급의 바닥값이다."""
    out = [(f"{t}:base", t, ()) for t in TIERS]
    for t in TIERS:
        for a, (_f, _label, _unit, bands) in AXES.items():
            out += [(key_of(t, ((a, b),)), t, ((a, b),)) for b in bands[t]]
        out += [(key_of(t, ps), t, ps) for ps in COMBOS[t]]
    return out


def label(tier, parts):
    if not parts:
        return f"{tier}등급 등급 바닥"
    return f"{tier}등급 " + " & ".join(
        f"{AXES[a][1]} {b:g}{AXES[a][2]}+" for a, b in parts)


def look(api, job, rates, sample):
    """키 하나. 값 내는 방식은 서판과 같다 — 싼 매물 열 건의 최저·중앙값."""
    _key, tier, parts = job
    return sample(api, query(tier, parts), rates)


def compose(league, b, rates, seen):
    """페이지가 읽을 문서. 구간표를 같이 실어 보낸다 — 경로석에는 카탈로그 파일이 없고,
    화면은 이 파일 하나만 받아서 표를 그린다.

    지금 물어보는 키만 싣는다. 축이나 구간을 빼도 예전 값은 상태 파일(과 게시 파일에서
    받아 온 씨앗)에 그대로 남아 있어, 여기서 거르지 않으면 표에 안 나오는 값이 파일에만
    영영 따라다닌다."""
    b = {k: v for k, v in b.items() if k in {j[0] for j in jobs()}}
    ats = [v[0] for v in b.values() if v and v[0]]
    return {
        "schema": 1, "league": league, "publishedAt": int(time.time()),
        "updatedAt": max(ats) if ats else 0,
        "rates": {k: v for k, v in rates.items() if k != "exalted"},
        "progress": [seen, len(jobs())], "tiers": list(TIERS),
        "axes": [{"id": a, "label": label, "unit": unit,
                  "bands": {str(t): [float(x) for x in bands[t]] for t in TIERS}}
                 for a, (_f, label, unit, bands) in AXES.items()],
        # 조합은 등급마다 목록이 다르다. 화면은 둘을 합쳐 줄을 만들고, 그 등급에 없는
        # 조합 칸은 흐린 '-' 로 둔다(단독 구간에서 하던 것과 같다).
        "combos": [{"tier": t, "key": key_of(t, ps),
                    "parts": [[a, float(b)] for a, b in ps]}
                   for t in TIERS for ps in COMBOS[t]],
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
        for key, tier, parts in js:
            print(f"  {key:<20} {label(tier, parts)}")
        print(f"  키 {len(js)}개 · 45초 간격이면 한 바퀴 {len(js) * 45 / 60:.0f}분")
        return

    import tablet_prices as tp
    api = tp.Trade("Forbidden Rites")
    rates = tp.money(api, {"exalted": 1.0})
    print("  환산: " + " · ".join(f"1 {k} = {v} 엑잘" for k, v in rates.items() if k != "exalted"))
    ch = rates.get("chaos") or 1
    for n, job in enumerate(js[:args.probe], 1):
        _key, tier, parts = job
        rec = look(api, job, rates, tp.sample)
        med = f"{rec[4] / ch:.1f}카오스" if rec[4] is not None else "매물 없음"
        print(f"  [{n}/{args.probe}] {label(tier, parts):<40} 매물 {rec[1]:>6} · 중앙 {med}")
        if n < args.probe:
            time.sleep(args.gap)


if __name__ == "__main__":
    main()
