#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ko-KR CSV 더미 -> 웹용 KO->EN 사전(JSON) 생성."""
import csv, glob, os, json, gzip, base64, sys, unicodedata as ud
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ko2en import DEFAULT_DATA, body, strip_color, priority

# 아이템 '이름' 조합을 통째로 전개해둔 파일들. 옵션이 아니라 이름만 들어있고,
# 접두/베이스/접미 합성 규칙(compose)으로 베이스타입을 복원할 수 있어 웹 배포본에서 제외한다.
# 주의: 세계포식자/작열의총주교/금단의*/불가능한_탈출/허무의_산물/용송곳니 등은
#      이름이 아니라 실제 옵션 파일이므로 반드시 포함해야 한다.
NAME_FILES = {ud.normalize("NFC", x) for x in (
 "플라스크_이름.csv","POE1_기생체.csv","심연주얼.csv","결합된주얼.csv","POE1_팅크.csv",
 "POE2_마나_플라스크.csv","POE2_생명력_플라스크.csv","진청록색주얼.csv","진홍색주얼.csv",
 "코발트색주얼.csv","POE1_특수_플라스크.csv","스킬군주얼_이름.csv",
 "POE1_삿된_고유_아이템_번호.csv")}


def build(data_dir=DEFAULT_DATA, full=False):
    files = sorted(glob.glob(os.path.join(data_dir, "*.csv")))
    # 경로가 틀리면 glob 이 빈 목록을 주고 그대로 '빈 사전'이 만들어진다.
    # 배포본을 조용히 망가뜨리므로 여기서 멈춘다.
    if not files:
        raise SystemExit(f"번역 CSV 를 찾지 못했습니다: {data_dir}\n"
                         "한글 POB 의 Data/Translate/ko-KR 를 저장소 루트의 Data/ 로 두거나, "
                         "KO2EN_DATA 환경변수로 경로를 지정하세요.")
    tmpl, plain, alts = {}, {}, {}
    for f in files:
        b = ud.normalize("NFC", os.path.basename(f))
        if not full and b in NAME_FILES:
            continue
        p = priority(f)
        for row in csv.reader(open(f, encoding="utf-8-sig", newline="", errors="replace")):
            if len(row) < 2:
                continue
            en, ko = strip_color(row[0]).strip(), strip_color(row[1]).strip()
            if not en or not ko:
                continue
            if "{" in ko and "{" in en:
                tmpl.setdefault(body(ko), []).append((p, ko, en))
            else:
                alts.setdefault(ko, set()).add(en)
                c = plain.get(ko)
                if c is None or p < c[0]:
                    plain[ko] = (p, en)
    # 템플릿으로 유도 가능한 평문 항목은 버린다
    plain = {ko: v for ko, v in plain.items() if body(ko) not in tmpl}
    for v in tmpl.values():
        v.sort(key=lambda t: (t[0], -len(t[1])))
    amap = {ko: sorted(v) for ko, v in alts.items() if len(v) > 1 and ko in plain}
    return ({k: [[ko, en] for _p, ko, en in v] for k, v in tmpl.items()},
            {ko: en for ko, (_p, en) in plain.items()},
            amap)


if __name__ == "__main__":
    t, p, a = build()
    raw = json.dumps({"t": t, "p": p, "a": a}, ensure_ascii=False, separators=(",", ":")).encode()
    b64 = base64.b64encode(gzip.compress(raw, 9)).decode()
    open("dict.b64", "w").write(b64)
    print(f"bodies {len(t)}  plain {len(p)}  alts {len(a)}  "
          f"json {len(raw)/1e6:.1f}MB  b64 {len(b64)/1e6:.2f}MB")
