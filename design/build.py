#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
디자인 시스템 빌드.

  design/tokens.css   단일 출처
  design/parts/*.html 컴포넌트 본문 (첫 줄 <!--meta ...--> 로 카드 정보)
        │
        ├─> design/dist/*.html          자체완결 미리보기 (업로드 대상)
        └─> web/src/styles/tokens.css   사이트가 쓰는 토큰

미리보기는 카드 안에서 단독으로 렌더링되므로 공유 CSS 를 링크할 수 없다.
토큰을 각 파일에 심어 자체완결로 만들되, 출처는 tokens.css 하나로 둔다.
"""
import os, re, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PARTS = os.path.join(HERE, "parts")
DIST = os.path.join(HERE, "dist")

META_RE = re.compile(r"^<!--meta\s+(.*?)-->\s*", re.S)

SHELL = """<!-- @dsCard group="{group}" -->
<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<title>{name}</title>
<style>
{tokens}
*{{box-sizing:border-box}}
html,body{{margin:0}}
body{{
  background:var(--bg); color:var(--ink);
  font-family:var(--f-body); font-size:var(--t-base); line-height:1.65;
  -webkit-font-smoothing:antialiased; padding:24px;
}}
</style>
</head><body>
{body}
</body></html>
"""


def parse_meta(text):
    m = META_RE.match(text)
    if not m:
        raise SystemExit("첫 줄에 <!--meta ...--> 가 없습니다")
    meta = {}
    for chunk in m.group(1).split("|"):
        k, _, v = chunk.partition("=")
        meta[k.strip()] = v.strip()
    return meta, text[m.end():]


def main():
    tokens = open(os.path.join(HERE, "tokens.css"), encoding="utf-8").read()
    # :root{...} 만 남기고 주석 헤더는 그대로 둔다 (미리보기에서도 읽힌다)

    shutil.rmtree(DIST, ignore_errors=True)
    os.makedirs(DIST, exist_ok=True)

    cards = []
    for fn in sorted(os.listdir(PARTS)):
        if not fn.endswith(".html"):
            continue
        meta, body = parse_meta(open(os.path.join(PARTS, fn), encoding="utf-8").read())
        slug = re.sub(r"^\d+-", "", fn)
        out = SHELL.format(group=meta["group"], name=meta["name"], tokens=tokens, body=body.strip())
        open(os.path.join(DIST, slug), "w", encoding="utf-8").write(out)
        cards.append((slug, meta))
        print(f"  {slug:<22} {meta['group']:<12} {meta['name']}")

    # 사이트가 쓰는 토큰
    site = os.path.join(ROOT, "web", "src", "styles", "tokens.css")
    open(site, "w", encoding="utf-8").write(
        "/* design/tokens.css 에서 생성됨 — 직접 고치지 말 것.\n"
        "   고칠 곳은 design/tokens.css 이고, python3 design/build.py 로 갱신한다. */\n"
        + tokens
    )
    print(f"\n  미리보기 {len(cards)}개 → design/dist/")
    print(f"  사이트 토큰 → web/src/styles/tokens.css")


if __name__ == "__main__":
    main()
