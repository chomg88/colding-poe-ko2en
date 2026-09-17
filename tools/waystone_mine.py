#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
POE2 경로석 시세 — 내 경로석 값 추정 (로컬 리포트).

거래소에 걸어 둔 내 경로석을 계정으로 찾아, 수집기가 모은 구간별 시세로 하나씩 값을
매긴다. 결과는 .cache/tablet/waystone-mine-report.html (git 제외) — 사이트에는 올리지
않는다. 브라우저는 거래 API 를 부를 수 없다(CORS).

서판(tools/tablet_mine.py)과 무엇이 다른가
──────────────────────────────────────────
서판 값은 붙은 옵션 문구에서 나서 카탈로그로 문구를 맞춰야 했다. 경로석 값은 **아이템에
찍힌 수치**에서 나므로 맞출 문구가 없다. 매물의 explicit 은 전부 몬스터를 세게 만드는
위험 옵션이라 값의 근거가 못 되고, 읽을 것은 properties 다.

    부활 횟수 0 · 아이템 희귀도 +23% · 무리 규모 +15% · 몬스터 희귀도 +42% · 몬스터 효율 +28%

그래서 구간표(축·구간·조합)를 여기에 다시 적지 않고 **시세 파일에 실려 온 것을 쓴다**.
화면(/tools/waystone/)이 하는 것과 같다 — 수집기가 축을 늘리거나 구간을 옮기면 이 도구도
따라간다. 여기 적어 두는 것은 축 id 와 아이템 수치 이름을 잇는 표 하나뿐이다.

어떻게 매기나
─────────────
축 하나 → 굴린 수치 이하 구간들 중 가장 비싼 중앙값. 구간이 높을수록 조건이 좁아지니 값이
떨어질 리 없는데, 매물 열 건짜리 표본이라 역전이 있다. 그래서 아래 구간 값까지 같이 본다.

조합 → 두 축이 다 닿는 조합 키가 있으면 그 값도 본다. 효율이 낀 조합은 단독보다 뚜렷이
비싸서 수집기가 그런 자리만 키로 두고 있다(waystone_prices.COMBOS).

경로석 하나 → max(그 등급의 바닥, 가장 비싼 단독, 가장 비싼 조합). 시세가 '이 수치 이상인
경로석' 검색이라 다른 축이 같이 굴러간 매물을 이미 포함한다 — 싼 축을 더해도 값이 오르지
않는다.

15·16등급만 값이 붙는다. 14등급 이하는 수집기가 아예 안 물어보므로 '추정 안 함' 이다.

요청
────
수집기와 같은 IP 한도를 나눠 쓴다. 검색은 한 번(100개가 넘으면 희귀도, 그다음 아이템
레벨을 반씩 쪼갠다), 상세는 10개에 한 번이다. 받은 것은 캐시해 두고, 다시 돌리면 요청 없이
최신 시세로만 다시 매긴다.

    python3 tools/waystone_mine.py --account "계정이름#1234"   # 처음 — 받아서 리포트
    python3 tools/waystone_mine.py                        # 캐시 + 최신 시세로 다시 매긴다
    python3 tools/waystone_mine.py --refresh              # 거래소에서 다시 받는다
"""
import argparse, json, os, re, statistics, subprocess, sys, time, urllib.parse
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tablet_prices as tp      # noqa: E402 — 거래소 호출 · 경로를 같이 쓴다

PICK = os.path.join(tp.STATE_DIR, "waystone-mine.json")     # 받아 둔 내 경로석
REPORT = os.path.join(tp.STATE_DIR, "waystone-mine-report.html")
LOCAL = os.path.join(tp.STATE_DIR, "waystone-prices.json")  # 이 맥이 수집기일 때
GAP_SEARCH = 5      # 검색 사이(초). 한도 헤더를 보고 더 늦추는 건 Trade 가 한다
GAP_FETCH = 3
DEAR = 2.0          # 호가가 추정의 이 배를 넘으면 '비쌈'
CHEAP = 0.5         # 이 배 밑이면 '쌈'
RARITIES = ("normal", "magic", "rare", "unique")

# 축 id → 아이템에 찍힌 수치의 이름. 시세 파일의 축 label 과 같지만, 이름이 바뀌어도
# 수치를 못 읽는 일이 없도록 여기서 못 박는다. 시세 파일에만 있는 축은 리포트가 일러 준다.
PROP = {"eff": "몬스터 효율", "rare": "몬스터 희귀도", "iir": "아이템 희귀도",
        "pack": "무리 규모", "bonus": "경로석 출현 확률"}
TIER = re.compile(r"\((\d+)등급\)")
NUM = re.compile(r"-?\d+(?:\.\d+)?")


# ── 받기 ─────────────────────────────────────────────────────────────────

def query(account, rarity=None, ilvl=None):
    """내 계정 · 경로석 분류. 오프라인 매물과 값 안 건 매물까지 전부."""
    tf = {"category": {"option": "map.waystone"}}
    if rarity:
        tf["rarity"] = {"option": rarity}
    if ilvl:
        tf["ilvl"] = {"min": ilvl[0], "max": ilvl[1]}
    return {"query": {"status": {"option": "any"},
                      "filters": {"type_filters": {"filters": tf},
                                  "trade_filters": {"filters": {
                                      "account": {"input": account},
                                      "sale_type": {"option": "any"}}}}},
            "sort": {"price": "asc"}}


def search(api, account, rarity=None, ilvl=None):
    """→ ([(검색id, [아이템 id])], 못 받은 수, 거래소가 센 전체). 검색 한 번에 id 가
    100개까지만 온다.
    넘으면 희귀도로, 그래도 넘으면 아이템 레벨을 반씩 쪼갠다. 가격으로는 못 쪼갠다 —
    내 매물은 같은 값에 몰려 있다. 서판과 달리 종류로는 못 쪼갠다(등급이 곧 종류라
    쪼개 봐야 등급 수만큼이고, 어차피 희귀도·레벨이 더 고르게 갈린다)."""
    L = urllib.parse.quote(api.league)
    s = api.call(f"/api/trade2/search/poe2/{L}", query(account, rarity, ilvl), "search")
    time.sleep(GAP_SEARCH)
    ids, total = s.get("result") or [], s.get("total", 0)
    label = " · ".join(str(x) for x in (rarity, ilvl and f"ilvl {ilvl[0]}-{ilvl[1]}") if x)
    print(f"  검색 {label or '전체'}: {total}개", flush=True)
    if total <= len(ids):
        return ([(s["id"], ids)] if ids else []), 0, total
    lo, hi = ilvl or (1, 100)
    if rarity is None:
        parts = [(r, ilvl) for r in RARITIES]
    elif lo < hi:
        mid = (lo + hi) // 2
        parts = [(rarity, (lo, mid)), (rarity, (mid + 1, hi))]
    else:
        return [(s["id"], ids)], total - len(ids), total    # 더 쪼갤 게 없다
    out, miss = [], 0
    for r, lv in parts:
        o, m, _ = search(api, account, r, lv)
        out, miss = out + o, miss + m
    return out, miss, total      # 쪼갠 쪽의 수는 안 센다 — 이 검색이 센 것이 전체다


def collect(league, account):
    api = tp.Trade(league)
    groups, miss, total = search(api, account)
    jobs = [(qid, ids[i:i + 10]) for qid, ids in groups for i in range(0, len(ids), 10)]
    items, seen = [], set()
    for n, (qid, chunk) in enumerate(jobs, 1):
        got = api.call(f"/api/trade2/fetch/{','.join(chunk)}?query={qid}", None, "fetch")
        for x in got.get("result") or []:
            if x and x.get("id") not in seen:
                seen.add(x["id"])
                items.append(x)
        print(f"  상세 {n}/{len(jobs)} · {len(items)}개", flush=True)
        if n < len(jobs):
            time.sleep(GAP_FETCH)
    if miss:
        print(f"  [못 받음] 더 쪼갤 수 없는 구간에서 {miss}개")
    return {"account": account, "league": league, "fetchedAt": int(time.time()),
            "total": total, "missed": max(0, total - len(items)), "items": items}


def load_pick():
    try:
        with open(PICK, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save_pick(pick):
    os.makedirs(tp.STATE_DIR, exist_ok=True)
    tmp = PICK + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(pick, f, ensure_ascii=False)
    os.replace(tmp, PICK)


def prices():
    """수집기가 마지막으로 올린 경로석 시세. 리그도 여기서 읽는다 — 경로석에는 리그를 적어
    둔 카탈로그가 없다.

    로컬 파일과 data 브랜치 중 **게시가 새것**을 쓴다. 서판 도구는 로컬을 먼저 보는데,
    수집기를 다른 기계로 옮기고 나면 여기 남은 옛 파일로 계속 매기게 된다 — 그 파일을
    지웠는지 기억하는 대신 둘을 견줘 고른다."""
    local = None
    try:
        with open(LOCAL, encoding="utf-8") as f:
            local = json.load(f)
    except (OSError, ValueError):
        pass
    remote = None
    try:
        subprocess.run(["git", "fetch", "-q", "origin", tp.BRANCH], cwd=tp.ROOT,
                       check=True, capture_output=True)
        remote = json.loads(subprocess.run(
            ["git", "show", f"origin/{tp.BRANCH}:waystone-prices.json"], cwd=tp.ROOT,
            check=True, capture_output=True, text=True).stdout)
    except (subprocess.CalledProcessError, ValueError) as e:
        if local is None:
            sys.exit(f"시세를 어디서도 못 읽었다: {e}")
    if local is None:
        return remote, "data 브랜치"
    if remote is None:
        return local, "로컬"
    if (remote.get("publishedAt") or 0) > (local.get("publishedAt") or 0):
        return remote, "data 브랜치"
    return local, "로컬"


# ── 매기기 ───────────────────────────────────────────────────────────────

def clean(name):
    """'[ItemRarity|아이템 희귀도]' → '아이템 희귀도'. 거래소가 붙이는 툴팁 표시를 걷는다."""
    return re.sub(r"\[(?:[^\]|]*\|)?([^\]]*)\]", r"\1", name or "")


class Book:
    """시세 파일 한 장. 구간표도 조합 목록도 이 파일에 실려 온다."""

    def __init__(self, doc):
        self.b = doc["b"]
        self.rates = dict(doc.get("rates") or {}, exalted=1.0)
        self.tiers = [int(t) for t in doc.get("tiers") or ()]
        self.axes = [a for a in doc.get("axes") or ()]
        self.bands = {a["id"]: {int(t): list(v) for t, v in a["bands"].items()} for a in self.axes}
        self.combos = {}                        # 등급 → [(키, [(축, 구간), ...])]
        for c in doc.get("combos") or ():
            self.combos.setdefault(int(c["tier"]), []).append(
                (c["key"], [(a, float(b)) for a, b in c["parts"]]))
        self.unknown = [a["id"] for a in self.axes if a["id"] not in PROP]

    def med(self, key):
        r = self.b.get(key)
        if not r or r[4] is None:
            return None
        return {"key": key, "v": r[4], "total": r[1], "n": r[2], "at": r[0], "qid": r[5]}

    def axis(self, tier, aid, val):
        """축 하나 — 굴린 수치가 닿는 구간들 중 가장 비싼 중앙값."""
        if val is None:
            return None
        ok = [b for b in self.bands.get(aid, {}).get(tier, ()) if val >= b - 1e-9]
        got = [dict(self.med(f"{tier}:{aid}:{b:g}") or {}, band=b) for b in ok
               if self.med(f"{tier}:{aid}:{b:g}")]
        return max(got, key=lambda x: x["v"]) if got else None

    def combo(self, tier, vals):
        """조합 — 두 축이 다 닿는 조합 키 중 가장 비싼 것."""
        got = []
        for key, parts in self.combos.get(tier, ()):
            if all(vals.get(a) is not None and vals[a] >= b - 1e-9 for a, b in parts):
                r = self.med(key)
                if r:
                    got.append(dict(r, parts=parts))
        return max(got, key=lambda x: x["v"]) if got else None

    def item(self, x):
        I, L = x.get("item") or {}, x.get("listing") or {}
        base = I.get("baseType") or I.get("typeLine") or ""
        m = TIER.search(base)
        tier = int(m.group(1)) if m else None

        props = {}
        for p in I.get("properties") or []:
            v = (p.get("values") or [[""]])[0][0]
            n = NUM.search(v or "")
            if n:
                props[clean(p.get("name"))] = float(n.group())
        vals = {a: props.get(PROP.get(a, "")) for a in self.bands}

        p = L.get("price") or {}
        rate = self.rates.get(p.get("currency"))
        ask = round(p["amount"] * rate, 3) if p.get("amount") and rate else None
        stash = L.get("stash") or {}
        row = {"id": x.get("id"), "base": base, "tier": tier,
               "rarity": I.get("rarity") or "", "ilvl": I.get("ilvl"),
               "corrupted": bool(I.get("corrupted")), "respawn": props.get("부활 횟수"),
               "stash": stash.get("name") or "", "x": stash.get("x"), "y": stash.get("y"),
               "indexed": L.get("indexed"),
               "askRaw": f"{p['amount']:g} {p['currency']}" if p.get("amount") else "",
               "ask": ask, "axes": [], "combo": None, "floor": None}

        if tier not in self.tiers:
            row["skip"] = f"{tier}등급 — 시세는 {'·'.join(str(t) for t in sorted(self.tiers))}등급만 모은다"
        elif not I.get("identified", True):
            row["skip"] = "미확인"

        if not row.get("skip"):
            floor = self.med(f"{tier}:base")
            row["floor"] = floor and floor["v"]
            for a in self.axes:
                aid = a["id"]
                row["axes"].append({"id": aid, "label": a["label"], "unit": a.get("unit", ""),
                                    "val": vals.get(aid), "p": self.axis(tier, aid, vals.get(aid))})
            row["combo"] = self.combo(tier, vals)
            best = max((c for c in row["axes"] if c["p"]),
                       key=lambda c: c["p"]["v"], default=None)
            cand = [c for c in ((floor and dict(floor, kind="floor")),
                                best and dict(best["p"], kind="axis", label=best["label"]),
                                row["combo"] and dict(row["combo"], kind="combo")) if c]
            top = max(cand, key=lambda c: c["v"]) if cand else None
            row["est"] = top and top["v"]
            row["why"] = top
            if best and top and top.get("kind") == "axis":
                best["top"] = True
            if row["est"] is None:
                row["skip"] = "시세 없음"

        if row.get("skip"):
            row["verdict"] = "skip"
            row.setdefault("est", None)
        elif ask is None:
            row["verdict"] = "none"
        else:
            row["ratio"] = round(ask / row["est"], 2)
            row["verdict"] = ("dear" if row["ratio"] > DEAR
                              else "cheap" if row["ratio"] < CHEAP else "fair")
        return row


# ── 리포트 ───────────────────────────────────────────────────────────────

def report(pick, doc, src, rows, unknown):
    data = {
        "account": pick["account"], "league": pick["league"],
        "fetchedAt": pick["fetchedAt"], "total": pick.get("total"), "missed": pick.get("missed", 0),
        "publishedAt": doc.get("publishedAt"), "updatedAt": doc.get("updatedAt"), "src": src,
        "rates": doc.get("rates") or {}, "dear": DEAR, "cheap": CHEAP,
        "progress": doc.get("progress"), "unknown": unknown,
        "trade": f"https://poe.kakaogames.com/trade2/search/poe2/{urllib.parse.quote(pick['league'])}",
        "rows": rows,
    }
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write(HTML.replace("__DATA__", blob))
    return REPORT


def fmt(ex, ch=None):
    """엑잘로 받아 카오스로 적는다 — 경로석은 카오스 몇 개짜리라 엑잘로는 자릿수만 길다."""
    if ex is None:
        return "-"
    v = ex / ch if ch else ex
    return f"{v:,.0f}" if v >= 100 else f"{v:.0f}" if v >= 10 else f"{v:.1f}" if v >= 1 else f"{v:.2f}"


def main():
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    ap = argparse.ArgumentParser(description="거래소에 걸어 둔 내 경로석 값 추정")
    ap.add_argument("--account", help="거래소 계정 (예: 계정이름#1234). 한 번 주면 캐시에 남는다")
    ap.add_argument("--refresh", action="store_true", help="거래소에서 다시 받는다")
    args = ap.parse_args()

    doc, src = prices()
    league = doc["league"]
    pick = load_pick()
    account = args.account or (pick or {}).get("account")
    if not account:
        sys.exit("처음에는 --account 로 계정을 준다 (예: --account \"계정이름#1234\")")
    if args.refresh or not pick or pick.get("account") != account or pick.get("league") != league:
        print(f"{league} · {account} 경로석을 받는다")
        pick = collect(league, account)
        save_pick(pick)
    else:
        print(f"받아 둔 {len(pick['items'])}개 "
              f"({time.strftime('%m-%d %H:%M', time.localtime(pick['fetchedAt']))}) — 다시 받으려면 --refresh")

    book = Book(doc)
    rows = [book.item(x) for x in pick["items"]]
    rows.sort(key=lambda r: -(r["est"] or -1))
    path = report(pick, doc, src, rows, book.unknown)

    ch = (doc.get("rates") or {}).get("chaos")
    v = Counter(r["verdict"] for r in rows)
    ests = [r["est"] for r in rows if r["verdict"] != "skip"]
    print(f"\n  시세 {time.strftime('%m-%d %H:%M', time.localtime(doc.get('publishedAt') or 0))} 게시 ({src})"
          f" · 진행 {'/'.join(str(x) for x in doc.get('progress') or [])}")
    print(f"  경로석 {len(rows)}개 (못 받음 {pick.get('missed', 0)})")
    print(f"  비쌈 {v['dear']} · 적정 {v['fair']} · 쌈 {v['cheap']} · 호가 없음 {v['none']} · 추정 안 함 {v['skip']}")
    if book.unknown:
        print(f"  [주의] 시세에 있는데 수치 이름을 모르는 축: {', '.join(book.unknown)}")
    if ests:
        print(f"  추정 합계 {fmt(sum(ests), ch)}카오스 · 중앙 {fmt(statistics.median(ests), ch)}카오스")
        asks = [r["ask"] for r in rows if r["verdict"] != "skip" and r["ask"] is not None]
        if asks:
            print(f"  호가 합계 {fmt(sum(asks), ch)}카오스")

    print("\n  추정 상위")
    for r in rows[:10]:
        why = r.get("why") or {}
        kind = {"floor": "등급 바닥", "axis": "단독", "combo": "조합"}.get(why.get("kind"), "")
        note = why.get("key", "")
        print(f"    {fmt(r['est'], ch):>7}카오스  {r['base']:<14} 호가 {r['askRaw'] or '-':<10} {kind} {note}")
    print(f"\n  리포트: {path}")


HTML = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>내 경로석 값 추정</title>
<style>
:root{--bg:#f6f6f3;--card:#fff;--fg:#1c1c1e;--dim:#6e6e73;--line:#e4e4df;--acc:#9a5b00;
  --dear:#b3261e;--dear-bg:#fdecea;--fair:#2e6b31;--fair-bg:#e7f3e8;--cheap:#1f5fbf;--cheap-bg:#e8f0fd;
  --mute-bg:#efefec;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#131315;--card:#1b1b1e;--fg:#ececef;--dim:#9b9ba1;
  --line:#2d2d31;--acc:#e3aa55;--dear:#ff8a80;--dear-bg:#3a1d1b;--fair:#8fcf92;--fair-bg:#1b2e1c;
  --cheap:#8ab4f8;--cheap-bg:#1b2638;--mute-bg:#26262a;color-scheme:dark}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
  font:14px/1.5 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Noto Sans KR",sans-serif}
main{max-width:1240px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:22px;margin:0 0 6px}
h2{font-size:15px;margin:28px 0 10px}
a{color:inherit}
.dim{color:var(--dim)}
.meta{color:var(--dim);font-size:13px;display:flex;flex-wrap:wrap;gap:2px 16px}
.meta b{color:var(--fg);font-weight:600}
.warn{margin:12px 0 0;padding:8px 12px;border-radius:8px;background:var(--dear-bg);color:var(--dear);font-size:13px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(128px,1fr));gap:10px;margin:18px 0 0}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;
  text-align:left;font:inherit;color:inherit;cursor:pointer}
.tile[aria-pressed=true]{outline:2px solid var(--fg);outline-offset:-2px}
.tile b{display:block;font-size:20px;font-variant-numeric:tabular-nums;line-height:1.3}
.tile span{color:var(--dim);font-size:12px}
.tile.dear b{color:var(--dear)} .tile.cheap b{color:var(--cheap)} .tile.fair b{color:var(--fair)}
.scroll{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:10px}
table{border-collapse:collapse;width:100%}
th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{font-size:12px;color:var(--dim);font-weight:600;white-space:nowrap}
tbody tr:last-child td{border-bottom:0}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.bar{display:flex;flex-wrap:wrap;gap:8px 12px;align-items:center;margin:0 0 10px}
.seg{display:inline-flex;flex-wrap:wrap;border:1px solid var(--line);border-radius:8px;overflow:hidden;background:var(--card)}
.seg button{border:0;background:none;color:var(--fg);padding:5px 10px;font:inherit;font-size:13px;cursor:pointer}
.seg button[aria-pressed=true]{background:var(--fg);color:var(--bg)}
select{font:inherit;font-size:13px;padding:5px 8px;border:1px solid var(--line);border-radius:8px;
  background:var(--card);color:var(--fg)}
.count{color:var(--dim);font-size:13px;margin-left:auto}
.v{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;white-space:nowrap;background:var(--mute-bg);color:var(--dim)}
.v.dear{background:var(--dear-bg);color:var(--dear)}
.v.fair{background:var(--fair-bg);color:var(--fair)}
.v.cheap{background:var(--cheap-bg);color:var(--cheap)}
.est{font-weight:700;font-size:15px}
.it b{font-weight:600}
.it .sub{font-size:12px;color:var(--dim)}
.rolls{display:grid;gap:1px;min-width:400px}
.roll{display:flex;gap:8px;align-items:baseline;font-size:13px}
.roll .t{flex:1;min-width:0;color:var(--dim)}
.roll .val{font-variant-numeric:tabular-nums;white-space:nowrap}
.roll.top .t,.roll.top .val{color:var(--fg);font-weight:600}
.roll.none .val{color:var(--dim)}
.band{font-size:11px;color:var(--dim);border:1px solid var(--line);border-radius:4px;padding:0 4px;flex:none}
.px{font-variant-numeric:tabular-nums;white-space:nowrap;color:var(--dim);flex:none;min-width:58px;text-align:right}
.roll.top .px{color:var(--acc);font-weight:600}
.go{font-size:12px;white-space:nowrap}
.empty{text-align:center;color:var(--dim);padding:24px}
details{margin-top:28px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px}
details summary{cursor:pointer;font-weight:600}
details li{margin:4px 0}
</style></head>
<body><main>
<h1>내 경로석 값 추정</h1>
<div class="meta" id="meta"></div>
<div id="warn"></div>
<div class="tiles" id="tiles"></div>

<h2>등급별</h2>
<div class="scroll"><table>
  <thead><tr><th>등급</th><th class="num">개수</th><th class="num">등급 바닥</th><th class="num">추정 중앙</th>
  <th class="num">추정 최고</th><th class="num">호가 중앙</th><th class="num">비쌈</th><th class="num">적정</th><th class="num">쌈</th></tr></thead>
  <tbody id="tiers"></tbody>
</table></div>

<h2>경로석 하나씩</h2>
<div class="bar">
  <div class="seg" id="seg-tier"></div>
  <div class="seg" id="seg-cur"><button data-v="ch">카오스</button><button data-v="ex">엑잘</button></div>
  <select id="sort" aria-label="정렬">
    <option value="est">추정가 높은 순</option>
    <option value="ask">호가 높은 순</option>
    <option value="ratio">호가/추정 높은 순</option>
    <option value="ratio-asc">호가/추정 낮은 순</option>
  </select>
  <span class="count" id="count"></span>
</div>
<div class="scroll"><table>
  <thead><tr><th class="num">#</th><th>경로석</th><th class="num">추정 <span data-unit></span></th>
  <th class="num">호가 <span data-unit></span></th><th class="num">호가/추정</th><th>판정</th>
  <th>수치 · 구간별 시세 <span data-unit></span></th><th></th></tr></thead>
  <tbody id="rows"></tbody>
</table></div>

<details>
<summary>어떻게 매겼나</summary>
<ul>
  <li><b>축 하나</b>: 굴린 수치 이하 구간들 중 가장 비싼 중앙값입니다. 수집기가 "이 등급 · 이 수치 이상"으로 즉시구입 매물을 검색해, 가장 싼 10건의 중앙값을 모아 둔 값입니다.</li>
  <li><b>조합</b>: 두 축이 다 닿는 조합 키가 있으면 그 값도 봅니다. 효율이 낀 조합만 단독보다 뚜렷이 비싸서, 수집기는 그런 자리만 키로 둡니다.</li>
  <li><b>경로석 하나</b>: max(등급 바닥, 가장 비싼 단독, 가장 비싼 조합)입니다. 시세 자체가 "이 수치 이상인 경로석"이라 다른 축이 같이 굴러간 매물을 이미 포함하므로, 싼 축을 더해도 값이 오르지 않습니다.</li>
  <li><b>구간 사이</b>: 구간은 "이 값 이상"이라, 45%를 굴려도 25+ 구간만 있으면 25+ 값으로 매깁니다. 그 구간 매물 무리의 값이지 이 경로석만의 값은 아닙니다 — 구간 맨 위에 걸친 것은 실제로 조금 더 비쌉니다.</li>
  <li><b>판정</b>: 호가가 추정의 <span id="k-dear"></span>배를 넘으면 비쌈, <span id="k-cheap"></span>배 밑이면 쌈입니다. 추정은 "지금 바로 살 수 있는 바닥값"에 가깝습니다.</li>
  <li><b>부활 횟수·부패</b>: 값을 가르지 않아 시세를 안 모읍니다. 표에는 적어만 둡니다.</li>
  <li><b>추정 안 함</b>: 시세를 모으지 않는 등급(14등급 이하)과 미확인 경로석입니다.</li>
</ul>
</details>
</main>
<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById("data").textContent);
const S = { tier: "", verdict: "", cur: "ch", sort: "est" };
const VERDICT = { dear: "비쌈", fair: "적정", cheap: "쌈", none: "호가 없음", skip: "추정 안 함" };
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const ch = D.rates.chaos;
const inCh = () => S.cur === "ch" && !!ch;
function money(ex) {
  if (ex == null) return "-";
  const v = inCh() ? ex / ch : ex;
  return v >= 100 ? Math.round(v).toLocaleString() : v >= 10 ? v.toFixed(0) : v >= 1 ? v.toFixed(1) : v.toFixed(2);
}
const ratio = (r) => r == null ? "" : (r >= 10 ? r.toFixed(0) : r.toFixed(1)) + "×";
const when = (s) => s ? new Date(s * 1000).toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "-";
const median = (a) => { if (!a.length) return null; const s = [...a].sort((x, y) => x - y), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
const priced = (r) => r.verdict !== "skip";

function header() {
  $("#meta").innerHTML = [
    `<span><b>${esc(D.account)}</b> · ${esc(D.league)}</span>`,
    `<span>매물 받은 시각 <b>${when(D.fetchedAt)}</b></span>`,
    `<span>시세 게시 <b>${when(D.publishedAt)}</b> (${esc(D.src)})</span>`,
    ch ? `<span>1 카오스 = <b>${Math.round(ch)}</b> 엑잘</span>` : "",
    D.rates.divine ? `<span>1 디바인 = <b>${Math.round(D.rates.divine)}</b> 엑잘</span>` : "",
  ].join("");
  const w = [];
  if (D.missed) w.push(`거래소 매물 ${D.missed}개를 받지 못했습니다 — 검색 한 번에 100개까지만 옵니다.`);
  if (D.unknown?.length) w.push(`시세에 있는데 아이템 수치 이름을 모르는 축이 있습니다: ${D.unknown.join(", ")}. 그 축은 값에 안 들어갔습니다.`);
  if (w.length) $("#warn").innerHTML = w.map((t) => `<p class="warn">${esc(t)}</p>`).join("");
  $("#k-dear").textContent = D.dear; $("#k-cheap").textContent = D.cheap;
}

function tiles() {
  const est = D.rows.filter(priced).reduce((a, r) => a + r.est, 0);
  const ask = D.rows.filter((r) => priced(r) && r.ask != null).reduce((a, r) => a + r.ask, 0);
  const n = (v) => D.rows.filter((r) => r.verdict === v).length;
  const t = [
    ["", "", D.rows.length, "경로석 전체"],
    ["", "", money(est), `추정 합계 (${inCh() ? "카오스" : "엑잘"})`],
    ["", "", money(ask), `호가 합계 (${inCh() ? "카오스" : "엑잘"})`],
    ["dear", "dear", n("dear"), `비쌈 · 추정의 ${D.dear}배 넘게`],
    ["fair", "fair", n("fair"), "적정"],
    ["cheap", "cheap", n("cheap"), `쌈 · 추정의 ${D.cheap}배 밑`],
    ["none", "", n("none"), "호가 없음"],
    ["skip", "", n("skip"), "추정 안 함"],
  ];
  $("#tiles").innerHTML = t.map(([v, cls, num, lab]) =>
    `<button type="button" class="tile ${cls}" data-verdict="${v}" aria-pressed="${!!v && S.verdict === v}"><b>${num}</b><span>${lab}</span></button>`).join("");
}

function tiers() {
  const by = {};
  for (const r of D.rows) (by[r.base] ||= []).push(r);
  const list = Object.entries(by).sort((a, b) => (b[1][0].tier ?? 0) - (a[1][0].tier ?? 0));
  $("#tiers").innerHTML = list.map(([base, rs]) => {
    const p = rs.filter(priced);
    const c = (v) => rs.filter((r) => r.verdict === v).length;
    return `<tr><td>${esc(base)}</td><td class="num">${rs.length}</td>
      <td class="num">${money(p.length ? p[0].floor : null)}</td>
      <td class="num">${money(median(p.map((r) => r.est)))}</td>
      <td class="num">${money(p.length ? Math.max(...p.map((r) => r.est)) : null)}</td>
      <td class="num">${money(median(p.filter((r) => r.ask != null).map((r) => r.ask)))}</td>
      <td class="num">${c("dear") || ""}</td><td class="num">${c("fair") || ""}</td><td class="num">${c("cheap") || ""}</td></tr>`;
  }).join("");
  const bases = ["", ...list.map(([b]) => b)];
  $("#seg-tier").innerHTML = bases.map((b) =>
    `<button type="button" data-v="${esc(b)}" aria-pressed="${S.tier === b}">${b ? esc(b.replace("경로석 ", "").replace(/[()]/g, "")) : "전체"}</button>`).join("");
}

function roll(a) {
  const val = a.val == null ? "-" : `+${a.val % 1 ? a.val : a.val.toFixed(0)}${a.unit}`;
  const band = a.p ? `<span class="band" title="이 구간으로 매겼습니다">${a.p.band % 1 ? a.p.band : a.p.band.toFixed(0)}${a.unit}+</span>` : "";
  const px = a.p ? `<span class="px" title="매물 ${a.p.total} · 값 낸 ${a.p.n}건 · ${when(a.p.at)}">${money(a.p.v)}</span>` : `<span class="px">-</span>`;
  return `<div class="roll${a.top ? " top" : ""}${a.val == null ? " none" : ""}">
    <span class="t">${esc(a.label)}</span><span class="val">${val}</span>${band}${px}</div>`;
}

function row(r, i) {
  const why = r.why || {};
  const qid = why.qid;
  const link = qid ? `<a class="go" href="${D.trade}/${esc(qid)}" target="_blank" rel="noopener" title="값을 매긴 근거의 비교 매물">비교 매물</a>` : "";
  const where = r.stash ? `${esc(r.stash)}${r.x != null ? ` (${r.x + 1}, ${r.y + 1})` : ""}` : "";
  const kind = { floor: "등급 바닥", axis: "단독", combo: "조합" }[why.kind] || "";
  const combo = r.combo ? `<div class="roll${why.kind === "combo" ? " top" : ""}">
      <span class="t">조합 ${esc(r.combo.parts.map(([a, b]) => `${a} ${b}+`).join(" & "))}</span>
      <span class="val"></span><span class="px" title="매물 ${r.combo.total} · ${when(r.combo.at)}">${money(r.combo.v)}</span></div>` : "";
  const floor = `<div class="roll${why.kind === "floor" ? " top" : ""}"><span class="t">등급 바닥</span>
      <span class="val"></span><span class="px">${money(r.floor)}</span></div>`;
  const sub = [r.rarity === "Magic" ? "마법" : r.rarity === "Rare" ? "희귀" : r.rarity === "Unique" ? "고유" : "일반",
    `ilvl ${r.ilvl ?? "-"}`, r.respawn != null ? `부활 ${r.respawn}` : "", r.corrupted ? "부패" : ""].filter(Boolean).join(" · ");
  return `<tr>
    <td class="num dim">${i + 1}</td>
    <td class="it"><b>${esc(r.base)}</b><div class="sub">${esc(sub)}</div>${where ? `<div class="sub">${where}</div>` : ""}${r.skip ? `<div class="sub">${esc(r.skip)}</div>` : ""}</td>
    <td class="num est">${priced(r) ? money(r.est) : "-"}</td>
    <td class="num" title="${esc(r.askRaw)}">${r.ask != null ? money(r.ask) : r.askRaw ? esc(r.askRaw) : "-"}</td>
    <td class="num">${ratio(r.ratio)}</td>
    <td><span class="v ${r.verdict}" ${r.skip ? `title="${esc(r.skip)}"` : ""}>${VERDICT[r.verdict]}</span>${kind ? `<div class="sub dim">${kind}</div>` : ""}</td>
    <td>${priced(r) ? `<div class="rolls">${r.axes.map(roll).join("")}${combo}${floor}</div>` : `<span class="dim">${esc(r.skip || "")}</span>`}</td>
    <td>${link}</td>
  </tr>`;
}

function render() {
  let list = D.rows.filter((r) => (!S.tier || r.base === S.tier)
    && (!S.verdict || r.verdict === S.verdict));
  const k = { est: (r) => -(priced(r) ? r.est : -1), ask: (r) => -(r.ask ?? -1),
              ratio: (r) => -(r.ratio ?? -1), "ratio-asc": (r) => r.ratio ?? Infinity }[S.sort];
  list = list.sort((a, b) => k(a) - k(b));
  for (const u of document.querySelectorAll("[data-unit]")) u.textContent = inCh() ? "카오스" : "엑잘";
  for (const b of document.querySelectorAll("#seg-cur button")) b.setAttribute("aria-pressed", String(b.dataset.v === S.cur));
  for (const b of document.querySelectorAll("#seg-tier button")) b.setAttribute("aria-pressed", String(b.dataset.v === S.tier));
  $("#count").textContent = `${list.length}개`;
  $("#rows").innerHTML = list.map(row).join("") || `<tr><td colspan="8" class="empty">조건에 맞는 경로석이 없습니다.</td></tr>`;
  tiles(); tiers();
}

document.addEventListener("click", (e) => {
  const t = e.target.closest(".tile[data-verdict]");
  if (t && t.dataset.verdict) { S.verdict = S.verdict === t.dataset.verdict ? "" : t.dataset.verdict; render(); return; }
  const b = e.target.closest("#seg-tier button, #seg-cur button");
  if (b) { S[b.parentElement.id === "seg-cur" ? "cur" : "tier"] = b.dataset.v; render(); }
});
$("#sort").addEventListener("change", (e) => { S.sort = e.target.value; render(); });
header(); render();
</script>
</body></html>
"""


if __name__ == "__main__":
    main()
