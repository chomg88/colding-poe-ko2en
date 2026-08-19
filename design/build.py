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

    # 한 화면에서 전부 훑어보는 대지. 카드 UI 없이 로컬에서 바로 확인할 때 쓴다.
    figs = "\n".join(
        f'  <figure>\n'
        f'    <figcaption><span class="g">{m["group"]}</span>{m["name"]}'
        f'<em>{m.get("subtitle","")}</em></figcaption>\n'
        f'    <iframe src="{slug}" width="{m.get("w",760)}" height="{m.get("h",480)}"'
        f' loading="lazy" title="{m["name"]}"></iframe>\n'
        f'  </figure>'
        for slug, m in cards
    )
    open(os.path.join(DIST, "index.html"), "w", encoding="utf-8").write(f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><title>POE 툴박스 디자인 시스템</title>
<style>
  body{{margin:0; padding:40px 28px; background:#0b0a09; color:#cfc7b8;
    font-family:"Pretendard","Apple SD Gothic Neo",-apple-system,sans-serif}}
  h1{{font-size:22px; font-weight:660; margin:0 0 4px}}
  .sub{{color:#7d7568; font-size:14px; margin:0 0 36px}}
  figure{{margin:0 0 40px}}
  figcaption{{display:flex; align-items:baseline; gap:10px; margin-bottom:10px;
    font-size:15px; font-weight:620}}
  figcaption .g{{font-size:10px; letter-spacing:.1em; text-transform:uppercase; color:#af6025;
    border:1px solid #5c3a19; border-radius:2px; padding:1px 7px; font-weight:700}}
  figcaption em{{font-style:normal; color:#5c554b; font-size:13px; font-weight:400}}
  iframe{{border:1px solid #2c2721; border-radius:4px; background:#0b0a09;
    display:block; max-width:100%}}
</style></head><body>
<h1>POE 툴박스 디자인 시스템</h1>
<p class="sub">{len(cards)}개 카드 · design/tokens.css 에서 생성 · 각 미리보기는 자체완결</p>
{figs}
</body></html>""")

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
