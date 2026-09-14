#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
POE2 서판 시세 — 수집기.

카탈로그(무엇을 물어볼지)를 읽어 카카오 거래소에 하나씩 물어보고, 답을

  tablet-prices.json  →  data 브랜치  →  raw.githubusercontent  →  페이지

로 올린다. 카탈로그는 tools/tablet_catalog.py 가 만들어 git 에 넣어 두고, 값은
여기서 만들어 사이트 빌드와 따로 올린다(DEPLOY.md 「서판 시세」).

왜 천천히 도는가
────────────────
거래소가 IP 로 한도를 건다. 검색 쪽이 제일 빡빡하다.

    검색   5:10:60, 15:60:300, 30:300:1800, 600:21600:3600
    상세   12:4:10, 16:12:300, 50:300:300, 1000:21600:1800
    환전   5:15:60, 10:90:300, 30:300:1800

읽는 법은 "600건까지 21600초(6시간) 안에, 넘으면 3600초 차단". 키 하나에 검색 1 +
상세 1 이므로 6시간에 600키가 천장이다. 45초에 하나(6시간 480키)면 천장에 닿지 않고,
한 바퀴 265키를 세 시간 남짓에 돈다. 응답 헤더의 잔량을 보고 스스로 더
늦추고, 그래도 막히면(429) 시키는 만큼 쉰다. 로그인은 쓰지 않는다 — 한도는 IP 로 걸린다.

무엇을 물어보는가
─────────────────
전부 물어보면 616키라 6시간에 안 들어온다. 두 단계로 나눈다.

    대표(rep)   옵션마다 가장 낮은 수치 하나씩              254키
    정밀(deep)  대표 중앙값이 200엑잘 이상인 옵션의 나머지 수치  ~11키

비싼 옵션만 수치별로 자세히 본다. 싼 옵션은 대표값 하나로 충분하다. 기준이 30엑잘일
때는 정밀이 227키라 한 바퀴가 여섯 시간이었고, 표의 줄마다 시각이 여섯 시간에 한 번
바뀌었다. 비싼 옵션만 가려내면 되므로 200엑잘로 올렸다.

    python3 tools/tablet_prices.py --once      # 한 바퀴만 돌고 끝 (시험용)
    python3 tools/tablet_prices.py             # 계속 돌면서 30분마다 게시
    python3 tools/tablet_prices.py --no-push   # 파일만 만들고 올리지는 않는다
"""
import argparse, glob, gzip, json, os, random, statistics, subprocess, sys, time
import urllib.error, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE) if os.path.basename(HERE) == "tools" else HERE
DIST = os.path.join(ROOT, "web", "public", "data")
STATE_DIR = os.path.join(ROOT, ".cache", "tablet")      # git 제외
STATE = os.path.join(STATE_DIR, "prices-state.json")
OUT = os.path.join(STATE_DIR, "tablet-prices.json")

BASE = "https://poe.kakaogames.com"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
SAMPLE = 10             # 키마다 볼 매물 수 — 상세 한 번에 10개까지 온다
DEEP_MIN = 200.0        # 대표 중앙값이 이 값(엑잘) 이상이면 나머지 수치도 본다
GAP = 45                # 키 사이 기본 간격(초). 검색 600:21600 에서 뒤로 계산했다
RATE_TTL = 3600         # 디바인·카오스 환산은 한 시간에 한 번
PUBLISH_EVERY = 1800    # 30분마다, 바뀐 게 있으면 올린다
BRANCH = "data"
WHO = ("tablet-collector", "tablet-collector@colding.xyz")

# 매물 값을 엑잘로 맞출 화폐와, 그 값을 어느 환전 장에서 읽는가.
#
# 환전 장은 허수 호가투성이다. '1엑잘에 카오스 1개' 처럼 1:1 로 걸어 둔 매물이 바닥에
# 박혀 있기도 하고(카오스 실제 값은 40엑잘쯤), 반대로 '1개 500엑잘' 도 흔하다. 그래서
# 가장 싼 호가 하나를 믿지 않고, 싼 쪽부터 호가 세 건이 15% 안에 모인 첫 자리를
# 시장가로 본다. 싸게 걸린 진짜 매물은 금방 팔려 나가므로 시세는 바닥 근처에 모이고,
# 허수는 혼자 떠 있다.
#
#   디바인  엑잘 장에서     319 · 320 · 330 → 320엑잘
#   카오스  디바인 장에서   0.118 · 0.124 · 0.125 디바인 → 41엑잘. 엑잘 장은 호가가
#           다섯 건뿐이고 1:1 허수가 바닥에 있어 모이는 자리가 없다.
#   바알    엑잘 장 바닥값. 호가가 3 · 10 · 30 · 100 · 500 이라 모이는 자리가 없다.
#           3엑잘은 옛 수집기의 2.4 와 같은 자릿수이고, 바알은 싸서 허수 바닥을 집어도
#           크게 틀리지 않는다 — 비싼 화폐에 바닥값을 쓰면 카오스처럼 40배 틀린다.
#
# 여기 없는 화폐(소멸·제왕 등)로 걸린 매물은 건너뛰고, 몇 개를 세었는지는 n 으로
# 싣는다. 서판 매물에서는 아직 못 봤다.
RATES = {
    "divine": ("exalted", "cluster"),
    "chaos": ("divine", "cluster"),
    "vaal": ("exalted", "floor"),      # 모이는 자리가 없으면 바닥값
}


# ── 거래소 ───────────────────────────────────────────────────────────────

class Trade:
    """거래소 호출. 한도 헤더를 보고 스스로 늦춘다."""

    def __init__(self, league, verbose=True):
        self.league = league
        self.verbose = verbose
        self.until = {}     # 정책 → 이 시각까지 쉰다

    def _wait(self, policy):
        t = self.until.get(policy, 0) - time.time()
        if t > 0:
            self.log(f"  {policy} 한도 — {t:.0f}초 쉰다")
            time.sleep(t)

    def _headers(self, policy, h):
        """'12:4:10' 은 4초에 12건, 넘으면 10초 차단. 남은 자리가 한 칸 이하로
        떨어지면 그 창이 끝날 때까지 쉰다 — 차단당하는 것보다 싸다."""
        rules, state = h.get("X-Rate-Limit-Ip"), h.get("X-Rate-Limit-Ip-State")
        if not rules or not state:
            return
        for rule, cur in zip(rules.split(","), state.split(",")):
            try:
                cap, win, _ = (int(x) for x in rule.split(":"))
                used, _, blocked = (int(x) for x in cur.split(":"))
            except ValueError:
                continue
            if blocked:
                self.until[policy] = max(self.until.get(policy, 0), time.time() + blocked)
            elif used >= cap - 1:
                self.until[policy] = max(self.until.get(policy, 0), time.time() + win)

    def call(self, path, body=None, policy="search", tries=3):
        url = f"{BASE}{path}"
        data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
        for attempt in range(tries):
            self._wait(policy)
            req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
            req.add_header("User-Agent", UA)
            req.add_header("Accept", "application/json")
            req.add_header("Accept-Encoding", "gzip")
            req.add_header("Referer", f"{BASE}/trade2/search/poe2/{urllib.parse.quote(self.league)}")
            if data:
                req.add_header("Content-Type", "application/json")
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    raw = r.read()
                    if r.headers.get("Content-Encoding") == "gzip":
                        raw = gzip.decompress(raw)
                    self._headers(policy, r.headers)
                    return json.loads(raw)
            except urllib.error.HTTPError as e:
                self._headers(policy, e.headers)
                if e.code == 429:
                    nap = int(e.headers.get("Retry-After") or 60)
                    self.until[policy] = time.time() + nap
                    self.log(f"  429 — {nap}초 쉬고 다시")
                    continue
                if 500 <= e.code < 600 and attempt < tries - 1:
                    time.sleep(5 * (attempt + 1))
                    continue
                raise RuntimeError(f"HTTP {e.code}")
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
                if attempt == tries - 1:
                    raise RuntimeError(str(getattr(e, "reason", e))[:80])
                time.sleep(5 * (attempt + 1))
        raise RuntimeError("한도에 계속 걸린다")

    def log(self, msg):
        if self.verbose:
            print(msg, flush=True)


def query_for(mod, base, band):
    """카탈로그 한 줄 → 거래소 검색 본문. 잔여 사용 횟수 10회 서판으로 못 박고,
    옵션 하나를 얹는다. stat id 가 둘인 옵션(성소·금고 등)은 문구로 가를 수 없어
    count(최소 1) 묶음으로 둘 다 건다."""
    if mod["kind"] == "existence":
        value = None
    elif mod["sign"] < 0:
        value = {"max": -band}      # 거래소에는 '증가' 의 음수로 올라 있다
    else:
        value = {"min": band}

    if len(mod["ids"]) > 1:
        group = {"type": "count", "value": {"min": 1},
                 "filters": [dict({"id": i}, **({"value": value} if value else {}))
                             for i in mod["ids"]]}
    else:
        f = {"id": mod["ids"][0]}
        if value:
            f["value"] = value
        group = {"type": "and", "filters": [f]}

    return {
        "query": {
            "status": {"option": "securable"},
            "type": mod["base"],
            "stats": [
                {"type": "and", "filters": [
                    {"id": base["usesStat"], "value": {"min": base["uses"], "max": base["uses"]}}]},
                group,
            ],
        },
        "sort": {"price": "asc"},
    }


def look(api, mod, base, band, rates):
    """키 하나. [본 시각, 매물 수, 값 낸 수, 최저, 중앙값, 검색id] 를 돌려준다."""
    league = urllib.parse.quote(api.league)
    s = api.call(f"/api/trade2/search/poe2/{league}", query_for(mod, base, band), "search")
    ids, qid, total = s.get("result") or [], s.get("id", ""), s.get("total", 0)
    if not ids:
        return [int(time.time()), total, 0, None, None, qid]

    got = api.call(f"/api/trade2/fetch/{','.join(ids[:SAMPLE])}?query={qid}", None, "fetch")
    ex = []
    for it in got.get("result") or []:
        p = ((it or {}).get("listing") or {}).get("price") or {}
        rate = rates.get(p.get("currency"))
        if rate and p.get("amount"):
            ex.append(round(p["amount"] * rate, 3))
    ex.sort()
    return [int(time.time()), total, len(ex), ex[0] if ex else None,
            round(statistics.median(ex), 3) if ex else None, qid]


def cluster(vals, n=3, tol=1.15):
    """싼 쪽부터 호가 n 건이 tol 배 안에 모인 첫 자리의 중앙값. 없으면 None."""
    vals = sorted(vals)
    for i in range(len(vals) - n + 1):
        if vals[i + n - 1] <= vals[i] * tol:
            return statistics.median(vals[i:i + n])
    return None


def book(api, have, want):
    """환전 장 하나 → {화폐: [그 화폐 1개가 have 로 몇 개인가, ...]}."""
    d = api.call(f"/api/trade2/exchange/poe2/{urllib.parse.quote(api.league)}",
                 {"query": {"status": {"option": "online"}, "have": [have], "want": want},
                  "sort": {"have": "asc"}, "engine": "new"}, "exchange")
    seen = {}
    for row in (d.get("result") or {}).values():
        for o in ((row or {}).get("listing") or {}).get("offers") or []:
            give, get = o.get("exchange") or {}, o.get("item") or {}
            if give.get("amount") and get.get("amount"):
                seen.setdefault(get.get("currency"), []).append(give["amount"] / get["amount"])
    return seen


def money(api, prev):
    """화폐 하나가 몇 엑잘인가(RATES 위 주석). 못 읽은 화폐는 지난 값을 그대로 둔다."""
    out = dict(prev, exalted=1.0)
    # 엑잘 장이 먼저다 — 디바인 장에서 읽은 값은 디바인 시세를 곱해야 엑잘이 된다.
    for have in ("exalted", "divine"):
        want = [c for c, (h, _) in RATES.items() if h == have]
        if not want or have not in out:
            continue
        try:
            seen = book(api, have, want)
        except RuntimeError as e:
            api.log(f"  환산({have} 장) 실패 — {e} (지난 값을 쓴다)")
            continue
        for c in want:
            vals = seen.get(c) or []
            v = cluster(vals)
            if v is None and RATES[c][1] == "floor" and vals:
                v = min(vals)
            if v is None:
                api.log(f"  환산({c}) 모이는 호가가 없다 — 지난 값을 쓴다")
                continue
            out[c] = round(v * out[have], 3)
    return out


# ── 할 일 정하기 ─────────────────────────────────────────────────────────

def catalog():
    files = sorted(glob.glob(os.path.join(DIST, "tablet-catalog-*.json.gz")))
    if not files:
        sys.exit("카탈로그가 없다 — 먼저 python3 tools/tablet_catalog.py 를 돌려라")
    if len(files) > 1:
        sys.exit(f"카탈로그가 둘 이상이다 — 옛것을 지워라: {[os.path.basename(f) for f in files]}")
    with gzip.open(files[0]) as f:
        return os.path.basename(files[0]), json.load(f)


def weave(rep, deep):
    """대표와 정밀을 남은 수에 비례해 섞는다.

    그냥 오래된 것부터 돌면 한쪽이 몰린다 — 기계를 옮기던 날 정밀 키가 전부 더 오래돼서
    세 시간 넘게 정밀만 봤다. 화면의 줄마다 보이는 시각·중앙값은 대표 키 것이라, 그동안
    표가 멈춘 것처럼 보인다. 한 바퀴에 걸리는 시간은 그대로지만 골고루 새로워진다."""
    out, i, j = [], 0, 0
    while i < len(rep) or j < len(deep):
        if j >= len(deep) or (i < len(rep) and i * len(deep) <= j * len(rep)):
            out.append(rep[i]); i += 1
        else:
            out.append(deep[j]); j += 1
    return out


def plan(cat, b):
    """물어볼 키 목록. 대표부터 채우고, 대표가 비싼 옵션만 나머지 수치로 넘어간다."""
    bases = {x["type"]: x for x in cat["bases"]}
    rep, deep = [], []
    for m in cat["mods"]:
        base = bases.get(m["base"])
        if not base:
            continue
        bands = m["bands"] or [None]
        for i, (key, band) in enumerate(zip(m["keys"], bands)):
            job = (key, m, base, band)
            if i == 0:
                rep.append(job)
            elif (b.get(m["keys"][0]) or [None] * 5)[4] is not None \
                    and b[m["keys"][0]][4] >= DEEP_MIN:
                deep.append(job)
    return rep, deep


# ── 올리기 ───────────────────────────────────────────────────────────────

def compose(cat, name, b, rates, rep, deep):
    seen = lambda jobs: sum(1 for k, *_ in jobs if b.get(k))
    # 이번 계획에 없는 키는 싣지 않는다 — 기준이 바뀌어 더는 안 보는 수치가 옛 값 그대로
    # 남아 있으면 화면에서 지금 시세처럼 읽힌다. 상태 파일에는 남겨 둔다.
    planned = {k for k, *_ in rep + deep}
    ats = [v[0] for v in b.values() if v and v[0]]
    return {
        "schema": 1, "league": cat["league"], "catalog": name,
        "publishedAt": int(time.time()), "updatedAt": max(ats) if ats else 0,
        "rates": {k: v for k, v in rates.items() if k != "exalted"},
        "progress": {"rep": [seen(rep), len(rep)], "deep": [seen(deep), len(deep)]},
        "deepMin": DEEP_MIN, "sample": SAMPLE,
        "b": {k: v for k, v in b.items() if k in planned},
    }


def publish(doc, push=True):
    """data 브랜치에 부모 없는 커밋 하나로 강제 푸시한다. 30분마다 쌓이면 안 되니
    기록을 남기지 않는다 — 사람이 이 브랜치에 커밋하지 않는다(DEPLOY.md)."""
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    if not push:
        return "파일만 (--no-push)"

    def git(*a, **kw):
        return subprocess.run(("git",) + a, cwd=ROOT, capture_output=True, text=True,
                              check=True, **kw).stdout.strip()

    blob = git("hash-object", "-w", OUT)
    tree = git("mktree", input=f"100644 blob {blob}\ttablet-prices.json\n")
    when = time.strftime("%Y-%m-%d %H:%M")
    env = dict(os.environ, GIT_AUTHOR_NAME=WHO[0], GIT_AUTHOR_EMAIL=WHO[1],
               GIT_COMMITTER_NAME=WHO[0], GIT_COMMITTER_EMAIL=WHO[1])
    commit = subprocess.run(
        ["git", "commit-tree", tree, "-m", f"서판 시세 {when} · {doc['league']}"],
        cwd=ROOT, capture_output=True, text=True, check=True, env=env).stdout.strip()
    git("push", "-f", "origin", f"{commit}:refs/heads/{BRANCH}")
    return f"{BRANCH} ← {commit[:7]}"


# ── 도는 부분 ────────────────────────────────────────────────────────────

def seed(league, name):
    """처음 도는 기계에서는 이미 올라가 있는 값을 씨앗으로 받는다. 한 바퀴가 여섯
    시간이라, 빈 상태로 올리면 그동안 페이지가 통째로 '대기' 로 보인다. 받은 값은
    오래된 것부터 차례로 덮인다."""
    try:
        subprocess.run(["git", "fetch", "-q", "origin", BRANCH], cwd=ROOT, check=True,
                       capture_output=True, text=True)
        raw = subprocess.run(["git", "show", f"origin/{BRANCH}:tablet-prices.json"], cwd=ROOT,
                             check=True, capture_output=True, text=True).stdout
        d = json.loads(raw)
    except (subprocess.CalledProcessError, ValueError) as e:
        print(f"  씨앗 없음 — 처음부터 모은다 ({str(e)[:60]})")
        return {}
    if d.get("league") != league or d.get("catalog") != name:
        print(f"  올라가 있는 값은 {d.get('league')}/{d.get('catalog')} — 처음부터 모은다")
        return {}
    print(f"  올라가 있는 값 {len(d.get('b') or {})}키를 씨앗으로 받았다")
    return d.get("b") or {}


def load_state(league, name):
    try:
        with open(STATE, encoding="utf-8") as f:
            s = json.load(f)
        if s.get("league") == league and s.get("catalog") == name:
            return s.get("b") or {}
        print("  리그나 카탈로그가 바뀌었다 — 값을 처음부터 다시 모은다")
        return {}
    except (OSError, ValueError):
        return seed(league, name)


def save_state(league, name, b):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"league": league, "catalog": name, "b": b}, f, ensure_ascii=False)
    os.replace(tmp, STATE)


def main():
    # launchd 로 띄우면 stdout 이 터미널이 아니라서 블록 버퍼링이 걸린다 — 로그가
    # 4KB 쌓일 때까지 안 보인다. 줄 단위로 바꿔 둔다.
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    ap = argparse.ArgumentParser(description="POE2 서판 시세 수집")
    ap.add_argument("--once", action="store_true", help="한 바퀴만 돌고 끝낸다")
    ap.add_argument("--no-push", action="store_true", help="파일만 만들고 올리지 않는다")
    ap.add_argument("--gap", type=float, default=GAP, help=f"키 사이 간격(초, 기본 {GAP})")
    ap.add_argument("--limit", type=int, help="이번 실행에서 볼 키 수 (시험용)")
    args = ap.parse_args()

    name, cat = catalog()
    api = Trade(cat["league"])
    b = load_state(cat["league"], name)
    print(f"{cat['league']} · 카탈로그 {name} · 이미 본 키 {len(b)}개")

    rates, rates_at, last_pub, dirty = {"exalted": 1.0}, 0.0, 0.0, False
    while True:
        if time.time() - rates_at > RATE_TTL:
            rates, rates_at = money(api, rates), time.time()
            print("  환산: " + " · ".join(f"1 {k} = {v} 엑잘"
                                        for k, v in rates.items() if k != "exalted"))

        rep, deep = plan(cat, b)
        # 오래 안 본 것부터. 아직 한 번도 안 본 키가 먼저다.
        for q in (rep, deep):
            q.sort(key=lambda j: (b.get(j[0]) or [0])[0])
        jobs = weave(rep, deep)
        if args.limit:
            jobs = jobs[:args.limit]
        print(f"  대표 {len(rep)} · 정밀 {len(deep)} — 이번 바퀴 {len(jobs)}키, "
              f"{len(jobs) * args.gap / 3600:.1f}시간쯤 걸린다")

        for n, (key, mod, base, band) in enumerate(jobs, 1):
            try:
                rec = look(api, mod, base, band, rates)
                b[key], dirty = rec, True
                save_state(cat["league"], name, b)
                print(f"  [{n}/{len(jobs)}] {key} {mod['base']} {mod['text'][:28]} "
                      f"· 매물 {rec[1]} · 중앙 {rec[4]}")
            except RuntimeError as e:
                old = b.get(key) or [int(time.time()), 0, 0, None, None, ""]
                b[key] = old[:6] + [str(e)]     # 화면이 칸에 '오류' 를 띄운다
                dirty = True
                print(f"  [{n}/{len(jobs)}] {key} 실패 — {e}")

            if dirty and time.time() - last_pub > PUBLISH_EVERY:
                doc = compose(cat, name, b, rates, rep, deep)
                try:
                    print("  게시:", publish(doc, not args.no_push))
                    last_pub, dirty = time.time(), False
                except subprocess.CalledProcessError as e:
                    print(f"  게시 실패 — {(e.stderr or '').strip()[:200]}")

            if n < len(jobs):
                time.sleep(args.gap * random.uniform(0.9, 1.1))

        doc = compose(cat, name, b, rates, rep, deep)
        try:
            print("  게시:", publish(doc, not args.no_push))
            last_pub, dirty = time.time(), False
        except subprocess.CalledProcessError as e:
            print(f"  게시 실패 — {(e.stderr or '').strip()[:200]}")
        if args.once:
            return


if __name__ == "__main__":
    main()
