#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
정적 호스팅용 배포본 생성.

  docs/index.html          ~20KB   사전 미포함
  docs/dict-core.json.gz   3.7MB   옵션·베이스타입·고유  (첫 화면에 필요)
  docs/dict-names.json.gz  1.0MB   희귀 아이템 이름     (백그라운드 지연 로딩)

.gz 를 그대로 받아 브라우저 DecompressionStream 으로 푼다.
서버에 Content-Encoding 설정이 필요 없어 GitHub Pages 등 어디든 그대로 올라간다.
"""
import gzip, hashlib, json, os, shutil, sys, unicodedata as ud
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_payload
from build_payload import build

HERE = os.path.dirname(os.path.abspath(__file__))
# GitHub Pages 의 /docs 소스. tools/ 안에서 실행해도 저장소 루트의 docs/ 에 쓴다.
ROOT = os.path.dirname(HERE) if os.path.basename(HERE) == "tools" else HERE
DIST = os.path.join(ROOT, "docs")

LOADER = '''
/* ---------- 사전 적재 ---------- */
const $veil = document.getElementById("veil");
const $note = document.getElementById("veil-note");

async function grab(url){
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} — HTTP ${res.status}`);
  const buf = new Uint8Array(await res.arrayBuffer());
  // 호스트가 Content-Encoding: gzip 을 붙이면 브라우저가 이미 풀어서 준다.
  // gzip 매직바이트(1f 8b)로 판별해 이중 해제를 피한다.
  const gz = buf[0] === 0x1f && buf[1] === 0x8b;
  const text = gz
    ? await new Response(new Blob([buf]).stream()
        .pipeThrough(new DecompressionStream("gzip"))).text()
    : new TextDecoder().decode(buf);
  return JSON.parse(text);
}

(async () => {
  try {
    const core = await grab("dict-core.json.gz");
    T = core.t; P = core.p; A = core.a;
    $veil.remove();
    document.getElementById("app").hidden = false;
    render();
    $in.focus();
    // 희귀 아이템 이름은 계산에 쓰이지 않으므로 뒤늦게 채워 넣는다
    try {
      Object.assign(P, await grab("dict-names.json.gz"));
      if ($in.value.trim()) render();
    } catch (e) { console.warn("이름 사전 생략:", e.message); }
  } catch (e) {
    $note.textContent = "사전을 불러오지 못했습니다 — " + e.message;
    $note.style.color = "var(--s-miss)";
    document.querySelector(".bar").remove();
  }
})();
'''


def main():
    os.makedirs(DIST, exist_ok=True)
    t, p, a = build()

    # 희귀 이름 파일을 뺀 상태로 한 번 더 빌드해서 '코어'를 구한다.
    # 단순히 이름 파일에 키가 있는지로 가르면 안 된다 — '척추 활' 처럼
    # 베이스타입(Spine Bow)이면서 희귀 이름(Spinal Arch)이기도 한 키가 있고,
    # 그런 키의 승자는 베이스타입이므로 코어에 남아야 한다.
    keep = set(build_payload.NAME_FILES)
    keep.add(ud.normalize("NFC", "희귀아이템이름.csv"))
    saved, build_payload.NAME_FILES = build_payload.NAME_FILES, keep
    try:
        t2, core_p, a2 = build()
    finally:
        build_payload.NAME_FILES = saved

    core = {"t": t, "p": core_p, "a": a}
    nm = {k: v for k, v in p.items() if k not in core_p}

    # 파일명에 내용 해시를 박아 영구 캐시(immutable)를 걸 수 있게 한다.
    # 리그마다 사전이 바뀌면 이름이 바뀌므로 캐시가 자동으로 무효화된다.
    for old in os.listdir(DIST):
        if old.startswith(("dict-core-", "dict-names-")):
            os.remove(os.path.join(DIST, old))
    stamped = {}
    for key, obj in (("core", core), ("names", nm)):
        raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode()
        # 해시는 압축 결과가 아니라 JSON 원문에서 뽑는다.
        # Python 3.11+ 의 gzip.compress(mtime=0) 은 zlib.compress(wbits=31) 로
        # 우회하는데 gzip 헤더의 OS 바이트를 zlib 빌드가 정한다. 압축본을 해시하면
        # 내용이 같아도 기계가 바뀌면 파일명이 바뀌어 캐시가 무의미하게 깨진다.
        blob = gzip.compress(raw, 9, mtime=0)
        h = hashlib.sha256(raw).hexdigest()[:10]
        fn = f"dict-{key}-{h}.json.gz"
        with open(os.path.join(DIST, fn), "wb") as f:
            f.write(blob)
        stamped[key] = fn
        print(f"  {fn:<32} {len(blob)/1e6:>5.2f} MB")

    with open(os.path.join(DIST, "_headers"), "w") as f:
        f.write("/dict-*.json.gz\n  Cache-Control: public, max-age=31536000, immutable\n"
                "/index.html\n  Cache-Control: public, max-age=300\n")

    tpl = open(os.path.join(HERE, "page.tpl.html"), encoding="utf-8").read()
    tpl = tpl.replace('const DICT_B64 = "__DICT_B64__";\n', "")
    head = tpl.index("/* ---------- 사전 적재 ---------- */")
    tail = tpl.index("</script>", head)
    tpl = tpl[:head] + LOADER.strip() + "\n" + tpl[tail:]
    tpl = tpl.replace('<div>번역 사전 여는 중 · 27만 항목</div>',
                      '<div id="veil-note">번역 사전 내려받는 중 · 3.7MB</div>')
    tpl = tpl.replace('"dict-core.json.gz"', f'"{stamped["core"]}"')
    tpl = tpl.replace('"dict-names.json.gz"', f'"{stamped["names"]}"')
    out = os.path.join(DIST, "index.html")
    open(out, "w", encoding="utf-8").write(tpl)
    print(f"  {'index.html':<22} {os.path.getsize(out)/1e3:>5.1f} KB")


if __name__ == "__main__":
    main()
