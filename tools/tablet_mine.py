#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
POE2 서판 시세 — 내 서판 값 추정 (로컬 리포트).

거래소에 걸어 둔 내 서판을 계정으로 찾아, 수집기가 모은 옵션별 시세로 하나씩 값을
매긴다. 결과는 .cache/tablet/mine-report.html (git 제외) — 사이트에는 올리지 않는다.
브라우저는 거래 API 를 부를 수 없어서(CORS) 사이트 페이지로는 만들 수 없다.

어떻게 매기나
─────────────
옵션 하나 → 굴린 수치 이하 구간들 중 가장 비싼 중앙값. 구간이 높을수록 조건이 좁아지니
값이 떨어질 리 없는데, 매물 열 건짜리 표본이라 역전이 있다(사원 '수정 추가' 5%+ 815,
8%+ 36엑잘). 그래서 아래 구간 값까지 같이 본다. 윗 구간을 모으지 않은 옵션(대표가 싸서
정밀을 안 봄)은 대표값으로 내려가고 '하한' 으로 표시한다.

서판 하나 → max(그 종류의 바닥, 가장 비싼 옵션). 시세가 '이 옵션이 붙은 서판' 검색이라
다른 옵션이 섞인 매물을 이미 포함한다 — 싼 옵션을 더해도 값이 오르지 않는다. 비싼 옵션이
둘 이상 붙은 서판은 조합 프리미엄을 모르므로 '조합' 으로 표시만 해 둔다.

요청
────
수집기와 같은 IP 한도를 나눠 쓴다. 검색은 서판 종류마다 한 번(100개 넘는 종류는 희귀도,
그다음 아이템 레벨로 쪼갠다), 상세는 10개에 한 번 — 368개면 검색 열몇 번, 상세 37번이다.
받은 것은 캐시해 두고, 다시 돌리면 요청 없이 최신 시세로만 다시 매긴다.

    python3 tools/tablet_mine.py --account "계정이름#1234"   # 처음 — 받아서 리포트
    python3 tools/tablet_mine.py                        # 캐시 + 최신 시세로 다시 매긴다
    python3 tools/tablet_mine.py --refresh              # 거래소에서 다시 받는다
"""
import argparse, json, os, re, statistics, subprocess, sys, time, urllib.parse
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tablet_prices as tp      # noqa: E402 — 거래소 호출 · 카탈로그 · 경로를 같이 쓴다

PICK = os.path.join(tp.STATE_DIR, "mine.json")          # 받아 둔 내 서판
REPORT = os.path.join(tp.STATE_DIR, "mine-report.html")
GAP_SEARCH = 5      # 검색 사이(초). 한도 헤더를 보고 더 늦추는 건 Trade 가 한다
GAP_FETCH = 3
DEAR = 2.0          # 호가가 추정의 이 배를 넘으면 '비쌈'
CHEAP = 0.5         # 이 배 밑이면 '쌈'
COMBO = 200.0       # 이 값(엑잘) 이상인 옵션이 둘 이상이면 '조합'
RARITIES = ("normal", "magic", "rare", "unique")


# ── 받기 ─────────────────────────────────────────────────────────────────

def query(account, typ=None, rarity=None, ilvl=None):
    """내 계정 · 서판 분류. 오프라인 매물과 값 안 건 매물까지 전부."""
    tf = {"category": {"option": "map.tablet"}}
    if rarity:
        tf["rarity"] = {"option": rarity}
    if ilvl:
        tf["ilvl"] = {"min": ilvl[0], "max": ilvl[1]}
    q = {"status": {"option": "any"},
         "filters": {"type_filters": {"filters": tf},
                     "trade_filters": {"filters": {"account": {"input": account},
                                                   "sale_type": {"option": "any"}}}}}
    if typ:
        q["type"] = typ
    return {"query": q, "sort": {"price": "asc"}}


def search(api, account, typ, rarity=None, ilvl=None):
    """→ ([(검색id, [아이템 id])], 못 받은 수). 검색 한 번에 id 가 100개까지만 온다.
    넘으면 희귀도로, 그래도 넘으면 아이템 레벨을 반씩 쪼갠다. 가격으로는 못 쪼갠다 —
    내 매물은 같은 값(1카오스)에 몰려 있다."""
    L = urllib.parse.quote(api.league)
    s = api.call(f"/api/trade2/search/poe2/{L}", query(account, typ, rarity, ilvl), "search")
    time.sleep(GAP_SEARCH)
    ids, total = s.get("result") or [], s.get("total", 0)
    label = " · ".join(str(x) for x in (typ, rarity, ilvl and f"ilvl {ilvl[0]}-{ilvl[1]}") if x)
    print(f"  검색 {label}: {total}개", flush=True)
    if total <= len(ids):
        return ([(s["id"], ids)] if ids else []), 0
    lo, hi = ilvl or (1, 100)
    if rarity is None:
        parts = [(r, ilvl) for r in RARITIES]
    elif lo < hi:
        mid = (lo + hi) // 2
        parts = [(rarity, (lo, mid)), (rarity, (mid + 1, hi))]
    else:
        return [(s["id"], ids)], total - len(ids)       # 더 쪼갤 게 없다
    out, miss = [], 0
    for r, lv in parts:
        o, m = search(api, account, typ, r, lv)
        out, miss = out + o, miss + m
    return out, miss


def collect(cat, account):
    api = tp.Trade(cat["league"])
    groups, miss = [], 0
    for b in cat["bases"]:
        g, m = search(api, account, b["type"])
        groups, miss = groups + g, miss + m
    # 카탈로그에 없는 서판 종류(이번 시즌에 빠진 것 등)는 종류별 검색에 안 걸린다.
    # 분류만 걸어 전체 수를 한 번 더 세어 맞춰 본다.
    whole = api.call(f"/api/trade2/search/poe2/{urllib.parse.quote(api.league)}",
                     query(account), "search").get("total", 0)

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
    return {"account": account, "league": cat["league"], "fetchedAt": int(time.time()),
            "total": whole, "missed": max(0, whole - len(items)), "items": items,
            "uniques": uniques(api, items)}


def uniques(api, items):
    """고유 서판은 붙은 옵션이 아니라 이름으로 값이 정해진다(카탈로그에도 이름만 있다).
    이름마다 즉시구입 매물을 싼 순으로 열 건 받아 둔다 — 수집기가 옵션에 쓰는 방식과 같다.
    화폐는 그대로 담고 엑잘 환산은 리포트를 만들 때 그때 환율로 한다."""
    L = urllib.parse.quote(api.league)
    names = sorted({(x["item"].get("baseType"), x["item"].get("name")) for x in items
                    if (x.get("item") or {}).get("rarity") == "Unique"})
    out = {}
    for base, name in names:
        s = api.call(f"/api/trade2/search/poe2/{L}",
                     {"query": {"status": {"option": "securable"}, "name": name, "type": base},
                      "sort": {"price": "asc"}}, "search")
        time.sleep(GAP_SEARCH)
        ids = (s.get("result") or [])[:10]
        offers = []
        if ids:
            got = api.call(f"/api/trade2/fetch/{','.join(ids)}?query={s['id']}", None, "fetch")
            time.sleep(GAP_FETCH)
            for it in got.get("result") or []:
                p = ((it or {}).get("listing") or {}).get("price") or {}
                if p.get("amount"):
                    offers.append([p["amount"], p.get("currency")])
        out[f"{base}|{name}"] = {"at": int(time.time()), "total": s.get("total", 0),
                                 "qid": s.get("id", ""), "offers": offers}
        print(f"  고유 {name} ({base}): 매물 {s.get('total', 0)}", flush=True)
    return out


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


def prices(name):
    """수집기가 마지막으로 올린 시세. 이 맥이 수집기면 로컬 파일, 아니면 data 브랜치."""
    try:
        with open(tp.OUT, encoding="utf-8") as f:
            doc, src = json.load(f), "로컬"
    except (OSError, ValueError):
        subprocess.run(["git", "fetch", "-q", "origin", tp.BRANCH], cwd=tp.ROOT,
                       check=True, capture_output=True)
        doc = json.loads(subprocess.run(
            ["git", "show", f"origin/{tp.BRANCH}:tablet-prices.json"], cwd=tp.ROOT,
            check=True, capture_output=True, text=True).stdout)
        src = "data 브랜치"
    if doc.get("catalog") != name:
        sys.exit(f"시세({doc.get('catalog')})가 지금 카탈로그({name})와 다르다 — 수집기가 한 바퀴 돌 때까지 기다린다")
    return doc, src


# ── 매기기 ───────────────────────────────────────────────────────────────

NUM = re.compile(r"\d+(?:\.\d+)?")


def clean(desc):
    """'[Rarity|희귀도]' → '희귀도'. 거래소가 옵션 문구에 붙이는 툴팁 표시를 걷는다."""
    return re.sub(r"\[(?:[^\]|]*\|)?([^\]]*)\]", r"\1", desc or "")


class Book:
    def __init__(self, cat, doc, uniq=None):
        self.b = doc["b"]
        self.uniq = uniq or {}
        self.rates = dict(doc.get("rates") or {}, exalted=1.0)
        self.idx = defaultdict(list)            # (서판 종류, stat id) → 카탈로그 옵션들
        self.floor = {}                         # 서판 종류 → 대표값 중 가장 싼 것
        for m in cat["mods"]:
            for i in m["ids"]:
                self.idx[(m["base"], i)].append(m)
            r = self.b.get(m["keys"][0])
            if r and r[4] is not None:
                self.floor[m["base"]] = min(self.floor.get(m["base"], r[4]), r[4])

    def mod_price(self, m, val):
        bands = m["bands"] or [None]
        ok = [(t, k) for t, k in zip(bands, m["keys"])
              if t is None or val is None or val >= t - 1e-9]
        ok = ok or [(bands[0], m["keys"][0])]       # 바닥보다 낮게 읽혔다 — 대표로
        seen = [(t, k) for t, k in ok if (self.b.get(k) or [None] * 5)[4] is not None]
        if not seen:
            return None
        t, k = max(seen, key=lambda x: self.b[x[1]][4])
        r = self.b[k]
        return {"v": r[4], "band": t, "total": r[1], "n": r[2], "at": r[0], "qid": r[5],
                # 수치가 닿는 가장 높은 구간을 못 봤으면 그보다 비쌀 수 있다
                "low": ok[-1][1] not in {kk for _, kk in seen}}

    def name_price(self, base, name):
        """고유 서판 — 같은 이름 매물 열 건의 중앙값(엑잘). 잔여 사용 횟수는 가리지 않는다."""
        u = self.uniq.get(f"{base}|{name}")
        ex = sorted(round(a * self.rates[c], 3) for a, c in (u or {}).get("offers") or []
                    if self.rates.get(c))
        if not ex:
            return None
        return {"v": round(statistics.median(ex), 3), "min": ex[0], "n": len(ex),
                "total": u.get("total"), "at": u.get("at"), "qid": u.get("qid") or ""}

    def mod(self, base, e, plain=False):
        text = clean(e.get("description"))
        tier = ((e.get("mods") or [{}])[0].get("tier") or "")
        aff = {"P": "prefix", "S": "suffix"}.get(tier[:1])
        row = {"text": text, "aff": aff}
        if plain:                       # 고유 서판 옵션 — 값은 이름으로 매긴다
            return row
        cands = self.idx.get((base, (e.get("hash") or "").removeprefix("stat.")), [])
        # 감독관의 '성소 1개 추가'(접두)와 '성소 #개 추가'(접미)는 stat id 가 같다 — 접두/접미로 가른다
        m = next((c for c in cands if c["affix"] == aff), cands[0] if cands else None)
        if not m:
            row["miss"] = True
            return row
        # 굴린 수치는 카탈로그 문구의 '#' 자리 숫자다. '#% 확률로 심연 4개' 처럼 고정 숫자가
        # 섞여 있어서, '#' 앞에 숫자가 몇 개 있는지 세어 그 자리를 읽는다.
        nums = [float(n) for n in NUM.findall(text)]
        at = len(NUM.findall(m["text"].split("#")[0]))
        row["val"] = nums[at] if len(nums) > at else None
        row["p"] = self.mod_price(m, row["val"])
        return row

    def item(self, x):
        I, L = x.get("item") or {}, x.get("listing") or {}
        # 마법 서판의 typeLine 에는 접사 이름이 붙는다("풍성한 의식 서판") — 종류는 baseType 이다
        base = I.get("baseType") or I.get("typeLine") or ""
        imp = " ".join(clean(m.get("description")) for m in I.get("implicitMods") or [])
        u = re.search(r"잔여 사용 횟수 (\d+)", imp)
        one = I.get("rarity") == "Unique"
        mods = [self.mod(base, e, one) for e in I.get("explicitMods") or []]

        p = L.get("price") or {}
        rate = self.rates.get(p.get("currency"))
        ask = round(p["amount"] * rate, 3) if p.get("amount") and rate else None
        stash = L.get("stash") or {}
        row = {"id": x.get("id"), "base": base, "name": I.get("name") or "",
               "rarity": I.get("rarity") or "", "ilvl": I.get("ilvl"),
               "uses": int(u.group(1)) if u else None,
               "stash": stash.get("name") or "", "x": stash.get("x"), "y": stash.get("y"),
               "indexed": L.get("indexed"),
               "askRaw": f"{p['amount']:g} {p['currency']}" if p.get("amount") else "",
               "ask": ask, "floor": self.floor.get(base), "mods": mods}

        priced = [m for m in mods if m.get("p")]
        top = max(priced, key=lambda m: m["p"]["v"]) if priced else None
        if top:
            top["top"] = True
        if one:
            row["uniq"] = self.name_price(base, I.get("name"))
            row["est"] = (row["uniq"] or {}).get("v")
            row["floor"] = None
        else:
            vals = [v for v in (row["floor"], top and top["p"]["v"]) if v is not None]
            row["est"] = max(vals) if vals else None
        row["combo"] = sum(1 for m in priced if m["p"]["v"] >= COMBO) >= 2

        if one and row["est"] is None:
            row["skip"] = "고유 서판 — 같은 이름 매물이 없다"
        elif one:
            pass                        # 이름으로 매겼다. 잔여 횟수는 아래에서 따지지 않는다
        elif not I.get("identified", True):
            row["skip"] = "미확인"
        elif row["uses"] != 10:
            row["skip"] = f"잔여 {row['uses']}회 — 시세는 10회 기준"
        elif row["est"] is None:
            row["skip"] = "시세 없음"

        if row.get("skip"):
            row["verdict"] = "skip"
        elif ask is None:
            row["verdict"] = "none"
        else:
            row["ratio"] = round(ask / row["est"], 2)
            row["verdict"] = ("dear" if row["ratio"] > DEAR
                              else "cheap" if row["ratio"] < CHEAP else "fair")
        return row


# ── 리포트 ───────────────────────────────────────────────────────────────

def report(pick, doc, src, rows):
    data = {
        "account": pick["account"], "league": pick["league"],
        "fetchedAt": pick["fetchedAt"], "total": pick.get("total"), "missed": pick.get("missed", 0),
        "publishedAt": doc.get("publishedAt"), "updatedAt": doc.get("updatedAt"), "src": src,
        "rates": doc.get("rates") or {}, "dear": DEAR, "cheap": CHEAP, "combo": COMBO,
        "trade": f"https://poe.kakaogames.com/trade2/search/poe2/{urllib.parse.quote(pick['league'])}",
        "rows": rows,
    }
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write(HTML.replace("__DATA__", blob))
    return REPORT


def fmt(ex):
    if ex is None:
        return "-"
    return f"{ex:,.0f}" if ex >= 100 else f"{ex:.0f}" if ex >= 10 else f"{ex:.1f}"


def main():
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    ap = argparse.ArgumentParser(description="거래소에 걸어 둔 내 서판 값 추정")
    ap.add_argument("--account", help="거래소 계정 (예: 계정이름#1234). 한 번 주면 캐시에 남는다")
    ap.add_argument("--refresh", action="store_true", help="거래소에서 다시 받는다")
    args = ap.parse_args()

    name, cat = tp.catalog()
    pick = load_pick()
    account = args.account or (pick or {}).get("account")
    if not account:
        sys.exit("처음에는 --account 로 계정을 준다 (예: --account \"계정이름#1234\")")
    if args.refresh or not pick or pick.get("account") != account or pick.get("league") != cat["league"]:
        print(f"{cat['league']} · {account} 서판을 받는다")
        pick = collect(cat, account)
        save_pick(pick)
    else:
        print(f"받아 둔 {len(pick['items'])}개 ({time.strftime('%m-%d %H:%M', time.localtime(pick['fetchedAt']))}) "
              f"— 다시 받으려면 --refresh")

    if not pick.get("uniques"):     # 고유 서판 값은 나중에 붙였다 — 옛 캐시에는 없다
        pick["uniques"] = uniques(tp.Trade(cat["league"]), pick["items"])
        save_pick(pick)

    doc, src = prices(name)
    book = Book(cat, doc, pick.get("uniques"))
    rows = [book.item(x) for x in pick["items"]]
    rows.sort(key=lambda r: -(r["est"] or -1))
    path = report(pick, doc, src, rows)

    v = Counter(r["verdict"] for r in rows)
    miss = sum(1 for r in rows for m in r["mods"] if m.get("miss"))
    low = sum(1 for r in rows for m in r["mods"] if m.get("top") and m["p"]["low"])
    ests = [r["est"] for r in rows if r["verdict"] != "skip"]
    print(f"\n  서판 {len(rows)}개 (거래소 전체 {pick.get('total')}, 못 받음 {pick.get('missed', 0)})")
    print(f"  비쌈 {v['dear']} · 적정 {v['fair']} · 쌈 {v['cheap']} · 호가 없음 {v['none']} · 추정 안 함 {v['skip']}")
    print(f"  조합 후보 {sum(r['combo'] for r in rows)} · 근거가 하한인 서판 {low} · 못 맞춘 옵션 {miss}")
    if ests:
        print(f"  추정 합계 {fmt(sum(ests))}엑잘 · 중앙 {fmt(statistics.median(ests))}엑잘")
    print("\n  추정 상위")
    for r in rows[:10]:
        t = next((m for m in r["mods"] if m.get("top")), None)
        why = f"고유 · {r['name']}" if r.get("uniq") else (t or {}).get("text", "")
        print(f"    {fmt(r['est']):>7}  {r['base']:<8} 호가 {r['askRaw'] or '-':<10} {why[:40]}")
    print(f"\n  리포트: {path}")


HTML = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>내 서판 값 추정</title>
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
main{max-width:1320px;margin:0 auto;padding:24px 16px 64px}
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
input,select{font:inherit;font-size:13px;padding:5px 8px;border:1px solid var(--line);border-radius:8px;
  background:var(--card);color:var(--fg)}
.count{color:var(--dim);font-size:13px;margin-left:auto}
.v{display:inline-block;padding:1px 8px;border-radius:999px;font-size:12px;white-space:nowrap;background:var(--mute-bg);color:var(--dim)}
.v.dear{background:var(--dear-bg);color:var(--dear)}
.v.fair{background:var(--fair-bg);color:var(--fair)}
.v.cheap{background:var(--cheap-bg);color:var(--cheap)}
.est{font-weight:700;font-size:15px}
.it b{font-weight:600}
.it .sub{font-size:12px;color:var(--dim)}
.mods{display:grid;gap:1px;min-width:380px}
.mod{display:flex;gap:6px;align-items:baseline;font-size:13px}
.mod .t{flex:1;min-width:0}
.mod.top .t{font-weight:600}
.aff{font-size:11px;color:var(--dim);border:1px solid var(--line);border-radius:4px;padding:0 4px;flex:none}
.px{font-variant-numeric:tabular-nums;white-space:nowrap;color:var(--dim);flex:none}
.mod.top .px{color:var(--acc);font-weight:600}
.tag{font-size:11px;color:var(--dim);white-space:nowrap}
.tag.low{color:var(--acc)}
.tag.miss{color:var(--dear)}
.combo{font-size:11px;color:var(--acc);border:1px solid currentColor;border-radius:4px;padding:0 4px;margin-left:4px}
.go{font-size:12px;white-space:nowrap}
.empty{text-align:center;color:var(--dim);padding:24px}
details{margin-top:28px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px}
details summary{cursor:pointer;font-weight:600}
details li{margin:4px 0}
</style></head>
<body><main>
<h1>내 서판 값 추정</h1>
<div class="meta" id="meta"></div>
<div id="warn"></div>
<div class="tiles" id="tiles"></div>

<h2>서판 종류별</h2>
<div class="scroll"><table>
  <thead><tr><th>종류</th><th class="num">개수</th><th class="num">추정 중앙</th><th class="num">추정 최고</th>
  <th class="num">호가 중앙</th><th class="num">비쌈</th><th class="num">적정</th><th class="num">쌈</th></tr></thead>
  <tbody id="types"></tbody>
</table></div>

<h2>서판 하나씩</h2>
<div class="bar">
  <div class="seg" id="seg-base"></div>
  <div class="seg" id="seg-cur"><button data-v="ex">엑잘</button><button data-v="div">디바인</button></div>
  <select id="sort" aria-label="정렬">
    <option value="est">추정가 높은 순</option>
    <option value="ask">호가 높은 순</option>
    <option value="ratio">호가/추정 높은 순</option>
    <option value="ratio-asc">호가/추정 낮은 순</option>
  </select>
  <input type="search" id="q" placeholder="옵션 · 이름 검색" aria-label="옵션 검색">
  <span class="count" id="count"></span>
</div>
<div class="scroll"><table>
  <thead><tr><th class="num">#</th><th>서판</th><th class="num">추정 <span data-unit></span></th>
  <th class="num">호가 <span data-unit></span></th><th class="num">호가/추정</th><th>판정</th>
  <th>옵션 · 옵션별 시세 <span data-unit></span></th><th></th></tr></thead>
  <tbody id="rows"></tbody>
</table></div>

<details>
<summary>어떻게 매겼나</summary>
<ul>
  <li><b>옵션 하나</b>: 굴린 수치 이하 구간들 중 가장 비싼 중앙값입니다. 수집기가 "잔여 10회 · 이 옵션 · 이 수치 이상"으로 즉시구입 매물을 검색해, 가장 싼 10건의 중앙값을 모아 둔 값입니다.</li>
  <li><b>하한</b>: 수치가 닿는 윗 구간을 모으지 않았습니다(대표값이 싸서 수치별로 안 봄). 실제로는 더 비쌀 수 있습니다.</li>
  <li><b>서판 하나</b>: max(그 종류의 바닥, 가장 비싼 옵션)입니다. 시세 자체가 "그 옵션이 붙은 서판"이라 다른 옵션이 섞인 매물을 이미 포함하므로, 싼 옵션을 더해도 값이 오르지 않습니다.</li>
  <li><b>조합</b>: 옵션 시세 기준 이상인 옵션이 둘 이상입니다. 조합 프리미엄은 이 표로 알 수 없어, 실제로는 추정보다 비쌀 수 있습니다.</li>
  <li><b>판정</b>: 호가가 추정의 <span id="k-dear"></span>배를 넘으면 비쌈, <span id="k-cheap"></span>배 밑이면 쌈입니다. 추정은 "지금 바로 살 수 있는 바닥값"에 가깝습니다.</li>
  <li><b>고유 서판</b>: 옵션이 아니라 이름으로 값이 정해지므로, 같은 이름의 즉시구입 매물 중 싼 열 건의 중앙값을 씁니다. 잔여 사용 횟수는 가리지 않았습니다 — 많이 쓴 서판은 이보다 쌉니다.</li>
  <li><b>추정 안 함</b>: 미확인, 잔여 사용 횟수가 10회가 아닌 서판, 같은 이름 매물이 없는 고유 서판입니다.</li>
</ul>
</details>
</main>
<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById("data").textContent);
const S = { base: "", verdict: "", cur: "ex", sort: "est", q: "" };
const VERDICT = { dear: "비쌈", fair: "적정", cheap: "쌈", none: "호가 없음", skip: "추정 안 함" };
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const div = D.rates.divine;
const inDiv = () => S.cur === "div" && !!div;
function money(ex) {
  if (ex == null) return "-";
  if (inDiv()) { const d = ex / div; return d >= 10 ? d.toFixed(0) : d >= 1 ? d.toFixed(1) : d.toFixed(2); }
  return ex >= 100 ? Math.round(ex).toLocaleString() : ex >= 10 ? ex.toFixed(0) : ex.toFixed(1);
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
    div ? `<span>1 디바인 = <b>${Math.round(div)}</b> 엑잘</span>` : "",
    D.rates.chaos ? `<span>1 카오스 = <b>${Math.round(D.rates.chaos)}</b> 엑잘</span>` : "",
  ].join("");
  if (D.missed) $("#warn").innerHTML = `<p class="warn">거래소에는 ${D.total}개가 있는데 ${D.missed}개를 받지 못했습니다. 검색 한 번에 100개까지만 와서 더 쪼갤 수 없는 구간이 남았습니다.</p>`;
  $("#k-dear").textContent = D.dear; $("#k-cheap").textContent = D.cheap;
}

function tiles() {
  const est = D.rows.filter(priced).reduce((a, r) => a + r.est, 0);
  const ask = D.rows.filter((r) => priced(r) && r.ask != null).reduce((a, r) => a + r.ask, 0);
  const n = (v) => D.rows.filter((r) => r.verdict === v).length;
  const t = [
    ["", "", D.rows.length, "서판 전체"],
    ["", "", money(est), `추정 합계 (${inDiv() ? "디바인" : "엑잘"})`],
    ["", "", money(ask), `호가 합계 (${inDiv() ? "디바인" : "엑잘"})`],
    ["dear", "dear", n("dear"), `비쌈 · 추정의 ${D.dear}배 넘게`],
    ["fair", "fair", n("fair"), "적정"],
    ["cheap", "cheap", n("cheap"), `쌈 · 추정의 ${D.cheap}배 밑`],
    ["none", "", n("none"), "호가 없음"],
    ["combo", "", D.rows.filter((r) => r.combo).length, "조합 후보"],
    ["skip", "", n("skip"), "추정 안 함"],
  ];
  $("#tiles").innerHTML = t.map(([v, cls, num, lab]) =>
    `<button type="button" class="tile ${cls}" data-verdict="${v}" aria-pressed="${!!v && S.verdict === v}"><b>${num}</b><span>${lab}</span></button>`).join("");
}

function types() {
  const by = {};
  for (const r of D.rows) (by[r.base] ||= []).push(r);
  const list = Object.entries(by).sort((a, b) => b[1].length - a[1].length);
  $("#types").innerHTML = list.map(([base, rs]) => {
    const p = rs.filter(priced);
    const c = (v) => rs.filter((r) => r.verdict === v).length;
    return `<tr><td>${esc(base)}</td><td class="num">${rs.length}</td>
      <td class="num">${money(median(p.map((r) => r.est)))}</td>
      <td class="num">${money(p.length ? Math.max(...p.map((r) => r.est)) : null)}</td>
      <td class="num">${money(median(p.filter((r) => r.ask != null).map((r) => r.ask)))}</td>
      <td class="num">${c("dear") || ""}</td><td class="num">${c("fair") || ""}</td><td class="num">${c("cheap") || ""}</td></tr>`;
  }).join("");
  const bases = ["", ...list.map(([b]) => b)];
  $("#seg-base").innerHTML = bases.map((b) =>
    `<button type="button" data-v="${esc(b)}" aria-pressed="${S.base === b}">${b ? esc(b.replace(" 서판", "")) : "전체"}</button>`).join("");
}

function mod(m, plain) {
  const aff = m.aff === "prefix" ? "접두" : m.aff === "suffix" ? "접미" : "";
  let px = "", tag = "";
  if (plain) tag = "";              // 고유 서판 — 옵션마다 값을 매기지 않는다
  else if (m.miss) tag = `<span class="tag miss" title="카탈로그에 없는 옵션">못 맞춤</span>`;
  else if (!m.p) tag = `<span class="tag">시세 없음</span>`;
  else {
    const tip = `구간 ${m.p.band ?? "존재"}+ · 매물 ${m.p.total} · ${when(m.p.at)}`;
    px = `<span class="px" title="${esc(tip)}">${money(m.p.v)}</span>`;
    if (m.p.low) tag = `<span class="tag low" title="수치가 닿는 윗 구간을 모으지 않았습니다 — 더 비쌀 수 있습니다">하한</span>`;
  }
  return `<div class="mod${m.top ? " top" : ""}">${aff ? `<span class="aff">${aff}</span>` : ""}<span class="t">${esc(m.text)}</span>${tag}${px}</div>`;
}

function row(r, i) {
  const top = r.mods.find((m) => m.top);
  const qid = top?.p?.qid || r.uniq?.qid;
  const link = qid ? `<a class="go" href="${D.trade}/${esc(qid)}" target="_blank" rel="noopener" title="값을 매긴 근거의 비교 매물">비교 매물</a>` : "";
  const why = r.uniq ? `<div class="mod top"><span class="aff">고유</span><span class="t">같은 이름 매물 ${r.uniq.total}건 · 싼 ${r.uniq.n}건의 중앙값</span><span class="px">${money(r.uniq.v)}</span></div>` : "";
  const where = r.stash ? `${esc(r.stash)}${r.x != null ? ` (${r.x + 1}, ${r.y + 1})` : ""}` : "";
  const v = `<span class="v ${r.verdict}" ${r.skip ? `title="${esc(r.skip)}"` : ""}>${VERDICT[r.verdict]}</span>${r.combo ? `<span class="combo" title="${D.combo}엑잘 이상 옵션이 둘 이상 — 조합 프리미엄은 반영되지 않았습니다">조합</span>` : ""}`;
  return `<tr>
    <td class="num dim">${i + 1}</td>
    <td class="it"><b>${esc(r.base)}</b><div class="sub">${esc(r.name)}${r.name ? " · " : ""}${r.rarity === "Magic" ? "마법" : r.rarity === "Rare" ? "희귀" : r.rarity === "Unique" ? "고유" : esc(r.rarity)} · ilvl ${r.ilvl ?? "-"}${r.uses != null && r.uses !== 10 ? ` · 잔여 ${r.uses}회` : ""}</div>${where ? `<div class="sub">${where}</div>` : ""}${r.skip ? `<div class="sub">${esc(r.skip)}</div>` : ""}</td>
    <td class="num est">${priced(r) ? money(r.est) : "-"}</td>
    <td class="num" title="${esc(r.askRaw)}">${r.ask != null ? money(r.ask) : r.askRaw ? esc(r.askRaw) : "-"}</td>
    <td class="num">${ratio(r.ratio)}</td>
    <td>${v}</td>
    <td><div class="mods">${why}${r.mods.map((m) => mod(m, !!r.uniq)).join("") || (why ? "" : `<span class="dim">옵션 없음 — 종류 바닥 ${money(r.floor)}</span>`)}</div></td>
    <td>${link}</td>
  </tr>`;
}

function render() {
  const q = S.q.trim();
  let list = D.rows.filter((r) => (!S.base || r.base === S.base)
    && (!S.verdict || (S.verdict === "combo" ? r.combo : r.verdict === S.verdict))
    && (!q || r.name.includes(q) || r.mods.some((m) => m.text.includes(q))));
  const k = { est: (r) => -(priced(r) ? r.est : -1), ask: (r) => -(r.ask ?? -1),
              ratio: (r) => -(r.ratio ?? -1), "ratio-asc": (r) => r.ratio ?? Infinity }[S.sort];
  list = list.sort((a, b) => k(a) - k(b));
  for (const u of document.querySelectorAll("[data-unit]")) u.textContent = inDiv() ? "디바인" : "엑잘";
  for (const b of document.querySelectorAll("#seg-cur button")) b.setAttribute("aria-pressed", String(b.dataset.v === S.cur));
  for (const b of document.querySelectorAll("#seg-base button")) b.setAttribute("aria-pressed", String(b.dataset.v === S.base));
  $("#count").textContent = `${list.length}개`;
  $("#rows").innerHTML = list.map(row).join("") || `<tr><td colspan="8" class="empty">조건에 맞는 서판이 없습니다.</td></tr>`;
  tiles(); types();
}

document.addEventListener("click", (e) => {
  const t = e.target.closest(".tile[data-verdict]");
  if (t && t.dataset.verdict) { S.verdict = S.verdict === t.dataset.verdict ? "" : t.dataset.verdict; render(); return; }
  const b = e.target.closest("#seg-base button, #seg-cur button");
  if (b) { S[b.parentElement.id === "seg-cur" ? "cur" : "base"] = b.dataset.v; render(); }
});
$("#sort").addEventListener("change", (e) => { S.sort = e.target.value; render(); });
$("#q").addEventListener("input", (e) => { S.q = e.target.value; render(); });
header(); render();
</script>
</body></html>
"""


if __name__ == "__main__":
    main()
