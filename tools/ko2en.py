#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
KO -> EN 아이템 텍스트 역번역기.

한글 POB(PoeCharm3)가 EN->KO 로 쓰는 Data/Translate/ko-KR/*.csv 를 그대로 뒤집어서,
게임 한글 클라이언트에서 복사한 아이템 텍스트를 영문 POB 가 먹을 수 있는 형태로 되돌린다.

알고리즘은 PoeCharm3.exe 안에 박혀있는 translator.js(zh->en) 와 동일:
  body(s) = s 에서 { } 숫자 . + - 를 전부 제거한 문자열   <- 인덱스 키
  후보 템플릿의 {n} 자리를 (\S+) 로 바꿔 매칭 -> 영문 템플릿에 값 렌더링
"""
import csv, glob, os, re, sys, argparse, unicodedata as ud
from collections import defaultdict

# 한글 POB 의 번역 CSV 폴더. 저장소 루트의 Data/Translate/ko-KR 를 기본으로 보고,
# 다른 곳에 두었으면 KO2EN_DATA 환경변수나 --data 로 넘긴다.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DATA = os.environ.get("KO2EN_DATA") or os.path.join(_ROOT, "Data", "Translate", "ko-KR")

# translator.js 의 function a(e){return e.replace(/[{}\d.+-]/gu,"")}
# 괄호는 원본에 없다. 게임의 '고급 아이템 정보'가 값 뒤에 범위를 붙이기 때문에
# ("공격 스킬의 원소 피해 38(37-42)% 증가") 인덱스 키에서 같이 지운다.
# 사전 쪽과 입력 쪽에 동일하게 적용되므로 매칭은 그대로 성립하고,
# 범위는 {0} 자리에 통째로 잡혀 영문에도 38(37-42) 로 그대로 실려 나간다.
BODY_RE = re.compile(r"[{}()\d.+\-]", re.UNICODE)
COLOR_RE = re.compile(r"\^[xX][0-9A-Fa-f]{6}|\^[0-9]")

def body(s):
    return BODY_RE.sub("", s)

def strip_color(s):
    return COLOR_RE.sub("", s)


class Tmpl:
    """translator.js 의 class i — {0} 자리표시자 파싱/렌더링"""
    SEG_RE = re.compile(r"\{(\d+)\}")

    def __init__(self, text):
        self.segments, self.params, last = [], [], 0
        for m in self.SEG_RE.finditer(text):
            self.segments.append(text[last:m.start()])
            self.params.append(int(m.group(1)))
            last = m.end()
        self.segments.append(text[last:])
        self._rx = re.compile("^" + r"(\S+)".join(re.escape(s) for s in self.segments) + "$")

    def parse(self, s):
        m = self._rx.match(s)
        if not m:
            return None
        return {n: v for n, v in zip(self.params, m.groups())}

    def render(self, vals):
        out = []
        for i, seg in enumerate(self.segments[:-1]):
            out.append(seg)
            out.append(vals.get(self.params[i], "{%d}" % self.params[i]))
        out.append(self.segments[-1])
        return "".join(out)


# 게임 한글 클라이언트의 프레임 키워드. CSV 에는 없으므로 별도 표.
FRAME_KEY = {
    "아이템 종류": "Item Class", "희귀도": "Rarity", "아이템 희귀도": "Rarity",
    "아이템 레벨": "Item Level",
    "소켓": "Sockets", "홈": "Sockets", "요구 사항": "Requirements", "요구사항": "Requirements",
    "레벨": "Level", "힘": "Str", "민첩": "Dex", "지능": "Int",
    "퀄리티": "Quality", "품질": "Quality", "방어도": "Armour",
    "회피": "Evasion Rating", "회피도": "Evasion Rating", "수호": "Ward",
    "에너지 보호막": "Energy Shield",
    "막기": "Chance to Block", "막기 확률": "Chance to Block",
    "물리 피해": "Physical Damage", "원소 피해": "Elemental Damage",
    "카오스 피해": "Chaos Damage", "혼돈 피해": "Chaos Damage",
    "초당 공격": "Attacks per Second", "치명타 확률": "Critical Strike Chance",
    "무기 범위": "Weapon Range", "메모": "Note", "노트": "Note",
    "초당 공격 횟수": "Attacks per Second", "공격 속도": "Attacks per Second",
    "무기 범위(칸)": "Weapon Range", "한계 사용 횟수": "Charges",
    "지도 등급": "Map Tier", "지도 티어": "Map Tier",
    "실험실": "Lab", "제한": "Limited to", "반경": "Radius", "무형성": "Intangibility",
    "회복": "Recovery", "소모": "Consumes",
}
FRAME_CLASS = {
    "활": "Bows", "지팡이": "Staves", "전투 지팡이": "Warstaves", "마법봉": "Wands", "홀": "Sceptres",
    "룬 단검": "Rune Daggers", "단검": "Daggers", "발톱": "Claws",
    "한손 검": "One Hand Swords", "찌르는 한손 검": "Thrusting One Hand Swords",
    "한손 도끼": "One Hand Axes", "한손 철퇴": "One Hand Maces",
    "양손 검": "Two Hand Swords", "양손 도끼": "Two Hand Axes", "양손 철퇴": "Two Hand Maces",
    "낚싯대": "Fishing Rods", "마나 플라스크": "Mana Flasks", "생명력 플라스크": "Life Flasks",
    "유틸리티 플라스크": "Utility Flasks", "복합 플라스크": "Hybrid Flasks",
    "주얼": "Jewels", "심연 주얼": "Abyss Jewels", "반지": "Rings", "허리띠": "Belts",
    "목걸이": "Amulets", "화살통": "Quivers", "방패": "Shields", "투구": "Helmets",
    "장갑": "Gloves", "장화": "Boots", "갑옷": "Body Armours", "지도": "Maps",
    "보조 젬": "Support Gems", "스킬 젬": "Skill Gems",
}
FRAME_VAL = {
    "일반": "Normal", "마법": "Magic", "희귀": "Rare", "고유": "Unique",
    "젬": "Gem", "화폐": "Currency", "점술 카드": "Divination Card",
}
FRAME_FLAG = {
    "타락됨": "Corrupted", "타락": "Corrupted",
    "감정되지 않음": "Unidentified", "미감정": "Unidentified",
    "거울 복제됨": "Mirrored", "복제됨": "Mirrored", "반사된": "Mirrored",
    "분열됨": "Split", "분할됨": "Split",
    "쉐이퍼 아이템": "Shaper Item", "엘더 아이템": "Elder Item",
    "정복자 아이템": "Warlord Item", "구원자 아이템": "Redeemer Item",
    "성전사 아이템": "Crusader Item", "사냥꾼 아이템": "Hunter Item",
    "합성 아이템": "Synthesised Item", "균열 아이템": "Fractured Item",
}
# 한글 클라이언트도 이 표기는 영문 그대로 찍는다 -> 있는 그대로 통과시킨다
SUFFIX_EN = {"implicit","crafted","enchant","fractured","scourge","synthesised",
             "veiled","augmented","rune","desecrated","corrupted"}
# 어미 접미사 (내재) 등
SUFFIX = {
    "내재": "implicit", "제작됨": "crafted", "제작": "crafted",
    "인챈트": "enchant", "각인": "enchant",
    "균열": "fractured", "합성": "synthesised", "스컬지": "scourge",
}
# 베이스타입 앞에 붙는 접두
BASE_PREFIX = [("상급 ", "Superior "), ("정교한 ", "Superior "),
               ("결합된 ", "Synthesised "), ("합성 ", "Synthesised ")]

SUFFIX_RE = re.compile(r"^(.*?)\s*\((.+?)\)\s*$")

# ---------------------------------------------------------------------------
# 게임의 '고급 아이템 정보 표시' 로 붙는 문구들. 전부 클라이언트가 찍는 것이라
# CSV 에 없다. 거래소 복사본에는 안 나오지만 게임에서 Ctrl+C 하면 항상 딸려온다.
# ---------------------------------------------------------------------------

# 촉매가 붙은 장신구: "퀄리티 (저항 속성 부여): +20% (augmented)"
# 게임은 '속성 부여', 한글 POB 는 '보정/속성 향상' 으로 쓴다. 둘 다 받는다.
QUAL_TAIL_RE = re.compile(r"\s*(?:속성 부여|속성 향상|보정)$")
QUAL_HEAD = {
    "공격": "Attack", "능력치": "Attribute", "시전": "Caster", "주문": "Caster",
    "카오스": "Chaos", "냉기": "Cold", "치명타": "Critical", "방어": "Defence",
    "원소 피해": "Elemental Damage", "원소": "Elemental", "화염": "Fire",
    "생명력 및 마나": "Life and Mana", "생명력": "Life", "번개": "Lightning",
    "마나": "Mana", "물리 및 카오스 피해": "Physical and Chaos Damage",
    "물리 및 카오스": "Physical and Chaos", "물리": "Physical",
    "저항": "Resistance", "속도": "Speed",
}

# "{ 대가의 제작 접두어 속성 부여 "개량된" (등급: 2) — 피해, 원소 }"
ADV_RE = re.compile(r"^\{\s*(.*?)\s*\}$")
ADV_HEAD_RE = re.compile(
    r'^(?P<kind>.*?속성\s*부여)'          # 대가의 제작 접두어 속성 부여
    r'(?:\s*"(?P<name>[^"]*)")?'           # "개량된"
    r'(?:\s*\((?P<paren>[^)]*)\))?'        # (등급: 2)
    r'(?P<rest>.*)$')                      # — 피해, 원소
ADV_KIND = {
    "고정": "Implicit", "내재": "Implicit", "비고정": "Explicit",
    "접두어": "Prefix", "접미어": "Suffix", "대가의 제작": "Master Crafted",
    "제작됨": "Crafted", "제작": "Crafted", "인챈트": "Enchant", "각인": "Enchant",
    "균열된": "Fractured", "균열": "Fractured", "합성된": "Synthesised",
    "합성": "Synthesised", "스컬지": "Scourge", "베일에 싸인": "Veiled",
    "베일": "Veiled", "타락된": "Corrupted", "타락": "Corrupted",
    "신성모독": "Desecrated", "룬": "Rune", "각인된": "Enchant",
}
# 속성 부여 뒤에 오는 태그 목록. 사전에도 있지만 다대일이라 되레 엉뚱하게 잡힌다.
ADV_TAG = {
    "피해": "Damage", "원소": "Elemental", "공격": "Attack", "주문": "Caster",
    "시전": "Caster", "방어력": "Defences", "방어도": "Armour", "회피": "Evasion",
    "에너지 보호막": "Energy Shield", "카오스": "Chaos", "저항": "Resistance",
    "화염": "Fire", "냉기": "Cold", "번개": "Lightning", "물리": "Physical",
    "생명력": "Life", "마나": "Mana", "속도": "Speed", "치명타": "Critical",
    "능력치": "Attribute", "소환수": "Minion", "광역": "Area",
    "발사체": "Projectile", "상태 이상": "Ailment", "막기": "Block",
    "회복": "Recovery", "명중": "Accuracy", "흡수": "Leech", "오라": "Aura",
    "저주": "Curse", "젬": "Gem", "홈": "Socket", "지속 시간": "Duration",
    "요구 사항": "Attribute", "인챈트": "Enchantment",
}
ADV_TIER_RE = re.compile(r"^\s*등급\s*:\s*(.+?)\s*$")
# 줄 끝에 붙는 주석. "심연 홈 1개 — 변경이 불가능한 값"
ADV_NOTE = {
    "변경이 불가능한 값": "Unscalable Value",
    "합성됨": "Synthesised", "분열됨": "Split",
}
ADV_PCT_RE = re.compile(r"^(\S+%)\s*(증가|감소)$")
DASH_RE = re.compile(r"\s+[—–]\s+")          # 고급 정보 구분자 (em/en dash)
DESC_RE = re.compile(r"^\(.*\)$")            # 통째로 괄호인 설명 줄


def priority(path):
    # macOS 는 파일명을 NFD 로 저장하므로 한글 패턴 비교 전에 NFC 로 정규화한다
    b = ud.normalize("NFC", os.path.basename(path))
    # 희귀 아이템 '이름' 조각(접두어/접미어) 파일. 'Arch'=활 처럼 실제 용어와
    # 심하게 충돌하므로 역방향에서는 최후순위로 밀어낸다. (접사=옵션 이므로 제외)
    if re.search(r"접두|접미|stats_words_(prefix|suffix)|Flask_tag", b): return 10
    if "희귀아이템이름" in b: return 8
    if "ALL_translations" in b:  return 0
    if "statDescriptions" in b:  return 1
    if b.startswith(("POE1_", "POE2_")): return 2
    if b in ("고유.csv", "기본유형.csv", "Gems_data.csv") or "PoeCharm_Items" in b or "PoeCharm_Uniques" in b:
        return 3
    if b in ("GUI.csv", "Main.csv", "CalcSections.csv", "CalcsTab.csv",
             "ConfigOptions.csv", "SkillsTab.csv", "TreeTab.csv"):
        return 9          # POB 자체 UI 문구 → 최후순위
    return 5


class Reverse:
    def __init__(self, data_dir, verbose=False):
        self.exact = {}                    # ko -> (prio, en)
        self.by_body = defaultdict(list)   # body(ko) -> [(prio, ko, en)]
        n = 0
        for f in sorted(glob.glob(os.path.join(data_dir, "*.csv"))):
            p = priority(f)
            with open(f, encoding="utf-8-sig", newline="", errors="replace") as fh:
                for row in csv.reader(fh):
                    if len(row) < 2:
                        continue
                    en, ko = strip_color(row[0]).strip(), strip_color(row[1]).strip()
                    if not en or not ko:
                        continue
                    n += 1
                    cur = self.exact.get(ko)
                    if cur is None or p < cur[0]:
                        self.exact[ko] = (p, en)
                    if "{" in ko and "{" in en:
                        self.by_body[body(ko)].append((p, ko, en))
        for v in self.by_body.values():
            v.sort(key=lambda t: (t[0], -len(t[1])))
        if verbose:
            print(f"# loaded {n} rows, {len(self.exact)} exact, {len(self.by_body)} bodies",
                  file=sys.stderr)

    def mod(self, ko):
        hit = self.exact.get(ko)
        if hit:
            return hit[1]
        for _p, kt, et in self.by_body.get(body(ko), ()):
            vals = Tmpl(kt).parse(ko)
            if vals is not None:
                return Tmpl(et).render(vals)
        return None

    def compose(self, s):
        """마법 아이템 이름 '접두 베이스 - 접미' 에서 베이스타입만 복원한다.
        접사는 별도 옵션 줄로 따로 오므로 POB 파싱에는 베이스타입이면 충분하다."""
        core = s.split(" - ")[0].strip()
        w = core.split()
        for i in range(len(w)):
            hit = self.exact.get(" ".join(w[i:]))
            if hit:
                return hit[1]
        return None

    # ---- 고급 아이템 정보 --------------------------------------------------

    def term(self, ko, table):
        """태그·접사이름처럼 짧은 낱말 하나. 손표 우선, 없으면 사전."""
        return table.get(ko) or self.exact.get(ko, (9, None))[1] or ko

    def note(self, ko):
        """줄 끝 주석: '변경이 불가능한 값', '20% 증가'"""
        ko = ko.strip()
        if ko in ADV_NOTE:
            return ADV_NOTE[ko]
        m = ADV_PCT_RE.match(ko)
        if m:
            return f"{m.group(1)} {'Increased' if m.group(2) == '증가' else 'Reduced'}"
        return self.mod(ko) or ko

    def advanced(self, inner):
        """'{ }' 안쪽. 접두어 속성 부여 "압도하는" (등급: 2) — 피해, 원소, 공격"""
        m = ADV_HEAD_RE.match(inner)
        if not m:
            return inner
        # '대가의 제작 접두어 속성 부여' -> Master Crafted Prefix Modifier
        head = QUAL_TAIL_RE.sub("", m.group("kind")).strip()
        words, out = head.split(), []
        while words:
            for n in (3, 2, 1):                    # 긴 낱말('대가의 제작') 먼저
                en = ADV_KIND.get(" ".join(words[:n]))
                if en:
                    out.append(en)
                    words = words[n:]
                    break
            else:
                out.append(words.pop(0))
        parts = [" ".join(out + ["Modifier"])]

        if m.group("name"):
            parts.append('"%s"' % self.term(m.group("name"), {}))
        if m.group("paren"):
            t = ADV_TIER_RE.match(m.group("paren"))
            parts.append("(%s)" % (f"Tier: {t.group(1)}" if t else m.group("paren")))
        for chunk in DASH_RE.split(m.group("rest")):
            chunk = chunk.strip()
            if not chunk:
                continue
            if "," in chunk or chunk in ADV_TAG:
                tags = [self.term(t.strip(), ADV_TAG) for t in chunk.split(",")]
                parts.append("— " + ", ".join(tags))
            else:
                parts.append("— " + self.note(chunk))
        return " ".join(parts)

    # ---- 한 줄 -------------------------------------------------------------

    def line(self, raw):
        s = strip_color(raw).strip()
        if not s or set(s) == {"-"}:
            return raw, "sep"

        m = ADV_RE.match(s)
        if m:
            return "{ %s }" % self.advanced(m.group(1)), "adv"

        # 옵션 줄 뒤에 붙는 주석을 떼어내고 본문만 번역한다.
        #   심연 홈 1개 — 변경이 불가능한 값
        tail = ""
        bits = DASH_RE.split(s, 1)
        if len(bits) == 2 and not DESC_RE.match(s):
            s, tail = bits[0].strip(), " — " + self.note(bits[1])

        en, kind = self._line(s, raw)
        return (en + tail if kind != "MISS" else raw), kind

    def _line(self, s, raw):
        # "키: 값" 형태
        if ": " in s or s.endswith(":"):
            k, _, v = s.partition(":")
            k, v = k.strip(), v.strip()
            ek = FRAME_KEY.get(k) or (self.exact.get(k + ":", (9, None))[1] or "").rstrip(":") or None
            # "퀄리티 (저항 속성 부여)" 처럼 괄호로 한정된 속성 이름
            if ek is None:
                q = SUFFIX_RE.match(k)
                if q and FRAME_KEY.get(q.group(1).strip()):
                    qt = QUAL_HEAD.get(QUAL_TAIL_RE.sub("", q.group(2)).strip())
                    if qt:
                        ek = f"{FRAME_KEY[q.group(1).strip()]} ({qt} Modifiers)"
            if ek:
                ev = ((FRAME_CLASS.get(v) if ek == "Item Class" else None)
                      or FRAME_VAL.get(v)
                      or (self.mod(v) if v and not re.fullmatch(r"[\d.,%+\- ]*", v) else None)
                      or v)
                return (f"{ek}: {ev}" if v else f"{ek}:"), "frame"

        if s in FRAME_FLAG:
            return FRAME_FLAG[s], "flag"

        # "모드 (내재)" 형태
        m = SUFFIX_RE.match(s)
        sfx = None
        core = s
        if m and (m.group(2) in SUFFIX or m.group(2).lower() in SUFFIX_EN):
            core = m.group(1)
            sfx = SUFFIX.get(m.group(2)) or m.group(2).lower()

        en = self.mod(core)
        if en is None:
            for kp, ep in BASE_PREFIX:            # 베이스타입 접두 처리
                if core.startswith(kp):
                    sub = self.mod(core[len(kp):])
                    if sub:
                        en = ep + sub
                        break
        if en is None:
            en = self.compose(core)
            if en is not None:
                return en, "base"
        if en is None:
            # ("심연 주얼"만 심연의 홈에 장착할 수 있습니다) 같은 설명 줄.
            # POB 는 읽지 않고 넘기므로 한글 그대로 통과시켜도 무해하다.
            if DESC_RE.match(s):
                return s, "desc"
            return raw, "MISS"
        return (f"{en} ({sfx})" if sfx else en), "ok"

    def text(self, t):
        return [self.line(l) for l in t.splitlines()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?")
    ap.add_argument("--data", default=DEFAULT_DATA)
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()
    src = open(a.file, encoding="utf-8").read() if a.file else sys.stdin.read()
    r = Reverse(a.data, verbose=a.debug)
    for en, how in r.text(src):
        print(f"{en}\t[{how}]" if a.debug else en)


if __name__ == "__main__":
    main()
