#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
POE2 서판 시세 — 카탈로그 생성.

  web/public/data/tablet-catalog-<해시>.json.gz   무엇을 물어볼지 (서판 종류 · 옵션 · 수치 구간)

값(시세)은 여기서 만들지 않는다. 거래소 검색은 로그인된 브라우저로만 안전하게 돌릴 수
있어서, 운영자 PC 의 수집기가 이 카탈로그를 읽어 돌리고 결과를 data 브랜치에 올린다
(DEPLOY.md 「서판 시세」). 카탈로그는 시즌이 바뀔 때만 다시 만들어 커밋한다.

재료는 둘이다.

    poe2db 서판 페이지(ModifiersCalc)   어떤 옵션이 붙는가 · 접두/접미 · 수치 범위
    카카오 거래소 data/stats, items     그 옵션의 거래 stat id · 서판 종류 · 잔여 횟수 implicit

poe2db 문구와 거래소 문구는 대부분 숫자만 다르다. 숫자를 '#' 으로 바꿔 맞추고, 안 맞는
것은 규칙 몇 개로 잡는다.

  - 거래소에만 붙는 괄호 설명: "골드 #% 증가(골드 더미)"
  - 부호: poe2db "+(30—40)%" / 거래소 "+#%"
  - 반대말: poe2db "비용 (20—30)% 감소" 는 거래소에 "#% 증가" 하나뿐이다 — 음수로 찾는다.
    느리게/빠르게도 같다.
  - 같은 문구에 stat id 가 둘인 것(성소·금고·에센스 1개 추가 등): 어느 쪽으로 붙어 나오는지
    문구로는 못 가른다. 둘 다 넣고, 수집기가 count(최소 1) 그룹으로 묶어 검색한다.
  - 그래도 안 맞으면 OVERRIDES 에 손으로 적는다. 빌드가 [못 맞춤] 으로 알려준다.

키
──
옵션 id 는 (서판 종류, 접두/접미, 문구) 의 해시다. 시세 파일은 구간 키
"<옵션 id>:<최소 수치>" 로 값을 싣는다. 키 목록을 카탈로그에 그대로 넣어 두므로 화면과
수집기가 숫자 표기(10 / 10.0)를 따로 맞출 필요가 없다.

고유 서판은 poe2db 서판 페이지에 없다. 이름만 받아 두고 옵션은 아직 넣지 않는다.

    python3 tools/tablet_catalog.py                  # 원본 캐시(하루)가 있으면 그걸로
    python3 tools/tablet_catalog.py --refresh        # poe2db·거래소 원본을 새로 받는다
    python3 tools/tablet_catalog.py --league "Forbidden Rites"
"""
import argparse, gzip, hashlib, html, json, os, re, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
# tools/ 안에서 실행해도 저장소 루트 기준으로 쓴다.
ROOT = os.path.dirname(HERE) if os.path.basename(HERE) == "tools" else HERE
DIST = os.path.join(ROOT, "web", "public", "data")
SRC = os.path.join(ROOT, ".cache", "tablet")          # 받은 원본 (git 제외)

LEAGUE = "Forbidden Rites"
KO_DATA = "https://poe.kakaogames.com/api/trade2/data"
POE2DB = "https://poe2db.tw/kr"
USER_AGENT = "colding-poe-tablet/1.0 (+https://colding.xyz)"
SRC_TTL = 24 * 3600
USES = 10       # 잔여 사용 횟수 10회짜리만 본다 — 일반 서판은 거의 다 10 이다

# poe2db 페이지 → 거래소 서판 종류. 잔여 횟수 implicit 은 문구의 이 낱말로 찾는다.
PAGES = {
    "Ritual_Tablet": ("의식 서판", "의식 제단"),
    "Abyss_Tablet": ("심연 서판", "심연 추가"),
    "Breach_Tablet": ("균열 서판", "저세상 균열"),
    "Delirium_Tablet": ("환영 서판", "환영의 거울"),
    "Expedition_Tablet": ("탐험 서판", "칼구르 탐험"),
    "Irradiated_Tablet": ("방사능 노출 서판", "방사능 노출 추가"),
    "Overseer_Tablet": ("감독관 서판", "지도 보스 강화"),
    "Temple_Tablet": ("사원 서판", "바알 등대"),
}
ANTONYMS = [("감소", "증가"), ("느리게", "빠르게")]
# 규칙으로 안 잡히는 것. 거래소 문구에 수치가 없어 존재 여부로만 찾는다.
OVERRIDES = {
    "지도 내 처음으로 발굴되는 룬 몬스터 #마리가 희귀 몬스터": "explicit.stat_3963944561",
}


# ── 원본 받기 ────────────────────────────────────────────────────────────

def _get(url, name, refresh):
    path = os.path.join(SRC, name)
    if not refresh and os.path.exists(path) and time.time() - os.path.getmtime(path) < SRC_TTL:
        with open(path, encoding="utf-8") as f:
            return f.read()
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        text = resp.read().decode("utf-8")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    time.sleep(1.0)     # poe2db 는 남의 사이트다 — 여덟 장을 몰아 받지 않는다
    return text


def _mods_view(page_html):
    m = re.search(r"new ModsView\((\{.*?\})\);", page_html, re.S)
    if not m:
        sys.exit("poe2db 페이지에 ModsView 데이터가 없다 — 페이지 구조가 바뀌었다")
    return json.loads(m.group(1))


# ── 문구 맞추기 ──────────────────────────────────────────────────────────

def _key(text):
    t = re.sub(r"\([^)]*[가-힣][^)]*\)", "", text)       # (골드 더미) 같은 설명
    t = re.sub(r"[+-]?(\d+(?:\.\d+)?|#)", "#", t)
    return re.sub(r"\s+", " ", t).strip()


def _stat_index(stats):
    idx = {}
    for g in stats["result"]:
        if g["id"] != "explicit":
            continue
        for e in g["entries"]:
            ids = idx.setdefault(_key(e["text"]), [])
            if e["id"] not in ids:
                ids.append(e["id"])
    return idx


def _uses_stats(stats):
    """서판 종류 → '잔여 사용 횟수 #회' implicit id."""
    entries = [e for g in stats["result"] if g["id"] == "implicit" for e in g["entries"]
               if "잔여 사용 횟수" in e["text"]]
    found = {}
    for base, word in PAGES.values():
        hit = [e["id"] for e in entries if word in e["text"]]
        if len(hit) != 1:
            sys.exit(f"{base} 잔여 횟수 implicit 을 못 가렸다({word}): {hit}")
        found[base] = hit[0]
    return found


def _mod_line(s):
    """poe2db 옵션 한 칸 → (문구, 범위들). 값이 붙은 첫 줄만 쓴다 — 값 없는 줄은
    같이 붙는 0 값 스탯이라 게임 화면에도 안 보인다."""
    s = re.sub(r'<span class="secondary">.*?</span>', "", s)
    parts = s.split("<br>")
    part = next((p for p in parts if "mod-value" in p), parts[0])
    t = html.unescape(re.sub(r"<[^>]+>", "", part)).replace("—", "-")
    ranges = [(float(a), float(b)) for a, b in re.findall(r"\((-?[\d.]+)-(-?[\d.]+)\)", t)]
    t = re.sub(r"\+?\((-?[\d.]+)-(-?[\d.]+)\)", "#", t)
    t = re.sub(r"\s+", " ", t).strip()
    return (t, ranges) if t else None


def _match(text, idx):
    """(stat id 들, 부호). 부호 -1 이면 거래소에는 반대말로 올라 있다 — 음수로 찾는다."""
    k = _key(text)
    if k in idx:
        return idx[k], 1
    for a, b in ANTONYMS:
        for x, y in ((a, b), (b, a)):
            if x in k and k.replace(x, y) in idx:
                return idx[k.replace(x, y)], -1
    return [], 1


def _bands(lo, hi):
    """검색할 최소 수치들. 구간 하나가 검색+조회 두 번이라 셋 안쪽으로 줄인다 —
    바닥, 가운데, 최상. 폭이 좁은 정수 범위(1~3회)는 전부."""
    if lo == hi:
        return [lo]
    if hi - lo <= 2 and lo == int(lo) and hi == int(hi):
        return [float(v) for v in range(int(lo), int(hi) + 1)]
    mid = (lo + hi) / 2
    mid = round(mid) if hi - lo >= 4 else round(mid * 2) / 2
    return sorted({lo, float(mid), hi})


def _num(v):
    return int(v) if v == int(v) else v


# ── 만들기 ───────────────────────────────────────────────────────────────

def build(league, refresh=False):
    os.makedirs(SRC, exist_ok=True)
    stats = json.loads(_get(f"{KO_DATA}/stats", "stats.json", refresh))
    items = json.loads(_get(f"{KO_DATA}/items", "items.json", refresh))
    idx = _stat_index(stats)
    uses = _uses_stats(stats)

    tablet_items = [e for g in items["result"] if g["id"] == "map" for e in g["entries"]
                    if e.get("type", "").endswith("서판")]
    trade_types = {e["type"] for e in tablet_items}
    uniques = [{"name": e["name"], "type": e["type"]} for e in tablet_items
               if e.get("flags", {}).get("unique")]

    bases, mods, unmatched, skipped = [], [], [], []
    seen = set()
    for page, (base, _word) in PAGES.items():
        if base not in trade_types:
            skipped.append(base)        # 이번 시즌 거래소에 없는 서판
            continue
        view = _mods_view(_get(f"{POE2DB}/{page}", f"{page}.html", refresh))
        bases.append({"type": base, "page": page, "usesStat": uses[base], "uses": USES})
        for m in view["normal"]:
            line = _mod_line(m["str"])
            if not line:
                continue
            text, ranges = line
            affix = "prefix" if m["ModGenerationTypeID"] == "1" else "suffix"
            mid = hashlib.sha1(f"{base}|{affix}|{text}".encode()).hexdigest()[:10]
            if mid in seen:
                continue
            seen.add(mid)
            shown = {"min": _num(ranges[0][0]), "max": _num(ranges[0][1])} if ranges else None
            if text in OVERRIDES:
                # 범위는 화면에 보여 줄 몫으로만 남기고 검색은 존재 여부로
                ids, sign, ranges = [OVERRIDES[text]], 1, []
            else:
                ids, sign = _match(text, idx)
            if not ids:
                unmatched.append(f"{base} · {text}")
                continue
            bands = _bands(*ranges[0]) if ranges else []
            mods.append({
                "id": mid, "base": base, "affix": affix, "text": text,
                "ids": ids, "sign": sign,
                "kind": "range" if ranges else "existence",
                "range": shown,
                "bands": [_num(t) for t in bands],
                "keys": [f"{mid}:{t:g}" for t in bands] or [f"{mid}:exists"],
            })

    catalog = {"schema": 1, "league": league, "uses": USES,
               "bases": bases, "mods": mods, "uniques": uniques}
    return catalog, unmatched, skipped


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="POE2 서판 시세 카탈로그 생성")
    ap.add_argument("--league", default=LEAGUE, help="거래소 리그 id (예: Forbidden Rites)")
    ap.add_argument("--refresh", action="store_true", help="poe2db·거래소 원본을 새로 받는다")
    args = ap.parse_args()

    catalog, unmatched, skipped = build(args.league, args.refresh)
    if not catalog["mods"]:
        sys.exit("옵션을 하나도 못 만들었다 — 원본이 바뀌었는지 확인하라")

    os.makedirs(DIST, exist_ok=True)
    for old in os.listdir(DIST):
        if old.startswith("tablet-catalog-"):
            os.remove(os.path.join(DIST, old))
    raw = json.dumps(catalog, ensure_ascii=False, separators=(",", ":")).encode()
    # 해시는 JSON 원문에서 뽑는다 (DEPLOY.md 함정 — gzip 헤더는 기계마다 다르다)
    fn = f"tablet-catalog-{hashlib.sha256(raw).hexdigest()[:10]}.json.gz"
    with open(os.path.join(DIST, fn), "wb") as f:
        f.write(gzip.compress(raw, 9, mtime=0))

    n_bands = sum(len(m["keys"]) for m in catalog["mods"])
    print(f"  {fn}  {os.path.getsize(os.path.join(DIST, fn)) / 1e3:.1f} KB")
    print(f"  {catalog['league']} · 서판 {len(catalog['bases'])}종 · 옵션 {len(catalog['mods'])}개 · "
          f"검색 구간 {n_bands}개 · 고유 서판 {len(catalog['uniques'])}종")
    for b in catalog["bases"]:
        n = [m for m in catalog["mods"] if m["base"] == b["type"]]
        print(f"    {b['type']:<10} 접두 {sum(m['affix'] == 'prefix' for m in n):>2} · "
              f"접미 {sum(m['affix'] == 'suffix' for m in n):>2}")
    for base in skipped:
        print(f"  [건너뜀] 이번 시즌 거래소에 없는 서판: {base}")
    for u in unmatched:
        print(f"  [못 맞춤] {u}  — OVERRIDES 에 stat id 를 적는다")


if __name__ == "__main__":
    main()
