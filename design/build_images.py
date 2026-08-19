#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
파비콘과 OG 이미지 생성. 색은 design/tokens.css 에서 읽어 온다.

  web/public/favicon.svg   탭 아이콘 (현대 브라우저)
  web/public/favicon.ico   구형·사파리 폴백
  web/public/og.png        공유 미리보기 1200x630
"""
import os, re, sys
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "web", "public")

KO = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
SERIF = "/System/Library/Fonts/Supplemental/Times New Roman.ttf"


def tokens():
    """tokens.css 에서 --이름:#hex 를 뽑는다. 색 정의는 한 곳뿐이어야 한다."""
    css = open(os.path.join(HERE, "tokens.css"), encoding="utf-8").read()
    return {m[0]: m[1] for m in re.findall(r"--([a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,8})", css)}


def font(path, size, index=0):
    try:
        return ImageFont.truetype(path, size, index=index)
    except OSError:
        return ImageFont.load_default(size)


def diamond(d, cx, cy, r, fill):
    d.polygon([(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], fill=fill)


def main():
    t = tokens()
    bg, accent, ink, muted = t["bg"], t["accent"], t["ink"], t["muted"]

    # ── favicon.svg — 브랜드 마름모. 헤더의 마크와 같은 도형이다
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="5" fill="{bg}"/>
  <path d="M16 6 L26 16 L16 26 L6 16 Z" fill="{accent}"/>
  <path d="M16 12 L20 16 L16 20 L12 16 Z" fill="{bg}"/>
</svg>
'''
    open(os.path.join(OUT, "favicon.svg"), "w", encoding="utf-8").write(svg)

    # ── favicon.ico — 여러 크기를 한 파일에
    sizes = [16, 32, 48, 64]
    imgs = []
    for s in sizes:
        im = Image.new("RGBA", (s * 8, s * 8), bg)
        d = ImageDraw.Draw(im)
        c = s * 4
        diamond(d, c, c, int(s * 3.2), accent)
        diamond(d, c, c, int(s * 1.3), bg)
        imgs.append(im.resize((s, s), Image.LANCZOS))
    imgs[0].save(os.path.join(OUT, "favicon.ico"), format="ICO",
                 sizes=[(s, s) for s in sizes], append_images=imgs[1:])

    # ── og.png — 공유 미리보기
    W, H = 1200, 630
    im = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(im)

    # 위쪽 액센트 실선. 카드에 쓴 것과 같은 신호
    d.rectangle([0, 0, W, 6], fill=accent)

    diamond(d, 88, 118, 16, accent)
    d.text((118, 100), "POE 툴박스", font=font(KO, 30, 1), fill=muted)

    d.text((80, 210), "아이템 변환기", font=font(KO, 84, 2), fill=ink)
    d.text((80, 330), "한글 클라이언트에서 복사한 아이템을", font=font(KO, 36), fill=muted)
    d.text((80, 384), "영문 Path of Building 형식으로", font=font(KO, 36), fill=muted)

    # 아이템 툴팁 흉내 — 등급색 테두리와 가운데 정렬된 이름
    bx, by, bw, bh = 760, 210, 360, 230
    d.rectangle([bx, by, bx + bw, by + bh], fill=t["sunken"], outline=t["rb-rare"], width=2)
    f_ser, f_mono = font(SERIF, 26), font(SERIF, 19)
    for txt, fnt, dy, col in [("Sol Guard", f_ser, 24, t["r-rare"]),
                              ("Ebony Tower Shield", f_ser, 58, t["r-rare"]),
                              ("+72 to maximum Life", f_mono, 118, t["st-ok"]),
                              ("49% increased Armour", f_mono, 148, t["st-ok"]),
                              ("+13% to all Resistances", f_mono, 178, t["st-ok"])]:
        w = d.textlength(txt, font=fnt)
        d.text((bx + (bw - w) / 2, by + dy), txt, font=fnt, fill=col)
    d.line([bx + 20, by + 100, bx + bw - 20, by + 100], fill=t["line-2"], width=1)

    d.text((80, 540), "colding.xyz", font=font(KO, 28), fill=t["faint"])
    im.save(os.path.join(OUT, "og.png"), optimize=True)

    for f in ("favicon.svg", "favicon.ico", "og.png"):
        p = os.path.join(OUT, f)
        print(f"  {f:<14} {os.path.getsize(p)/1024:>7.1f} KB")


if __name__ == "__main__":
    main()
