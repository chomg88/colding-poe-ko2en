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
import gzip, hashlib, json, os, sys, unicodedata as ud
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_payload
from build_payload import build

HERE = os.path.dirname(os.path.abspath(__file__))
# tools/ 안에서 실행해도 저장소 루트 기준으로 쓴다.
ROOT = os.path.dirname(HERE) if os.path.basename(HERE) == "tools" else HERE
DIST = os.path.join(ROOT, "web", "public", "data")

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

    hdr = os.path.join(os.path.dirname(DIST), "_headers")   # web/public/_headers
    with open(hdr, "w") as f:
        # Cloudflare Pages 는 매칭되는 규칙을 전부 이어붙인다. /data/* 는 /* 에도
        # 걸리므로 그냥 두면 Cache-Control 에 max-age 가 두 개 실린다.
        # '! 헤더명' 으로 앞서 붙은 값을 지우고 다시 넣는다.
        f.write(
            "/*\n"
            "  Cache-Control: public, max-age=600\n"
            "\n"
            "/data/*\n"
            "  ! Cache-Control\n"
            "  Cache-Control: public, max-age=31536000, immutable\n"
        )


if __name__ == "__main__":
    main()
