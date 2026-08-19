// PoeCharm3 의 역번역 규칙을 그대로 옮긴 엔진.
// 사전(T/P/A)에 의존하지 않는 상수·클래스는 모듈 최상단에 두고,
// 사전을 쓰는 함수는 createTranslator() 로 감싼다. 도구가 늘어나도
// 같은 엔진을 import 해서 쓸 수 있게 하기 위함이다.

/* ---------- PoeCharm3 translator.js 와 동일한 매칭 규칙 ---------- */
// 괄호는 원본 규칙에 없다. 게임의 '고급 아이템 정보'가 값 뒤에 범위를 붙이므로
// ("원소 피해 38(37-42)% 증가") 인덱스 키에서 같이 지운다. 사전·입력 양쪽에
// 똑같이 적용되니 매칭은 그대로고, 범위는 {0} 자리에 통째로 실려 나간다.
const BODY_RE  = /[{}()\d.+\-]/gu;                     // 인덱스 키: 숫자·자리표시자 제거
const COLOR_RE = /\^[xX][0-9A-Fa-f]{6}|\^\d/g;         // POB 색상코드
const body = s => s.replace(BODY_RE, "");
const stripColor = s => s.replace(COLOR_RE, "");
const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

class Tmpl {
  constructor(text){
    this.seg = []; this.par = [];
    let last = 0;
    for (const m of text.matchAll(/\{(\d+)\}/g)){
      this.seg.push(text.slice(last, m.index));
      this.par.push(+m[1]);
      last = m.index + m[0].length;
    }
    this.seg.push(text.slice(last));
    this.rx = new RegExp("^" + this.seg.map(esc).join("(\\S+)") + "$");
  }
  parse(s){
    const m = this.rx.exec(s);
    if (!m) return null;
    const o = {};
    this.par.forEach((n,i) => o[n] = m[i+1]);
    return o;
  }
  render(v){
    let out = "";
    for (let i = 0; i < this.par.length; i++)
      out += this.seg[i] + (v[this.par[i]] ?? `{${this.par[i]}}`);
    return out + this.seg[this.seg.length-1];
  }
}

/* ---------- 게임 클라이언트 프레임 문구 (CSV에 없어 별도 표) ---------- */
const FRAME_KEY = {
  "아이템 종류":"Item Class","희귀도":"Rarity","아이템 희귀도":"Rarity","아이템 레벨":"Item Level",
  "소켓":"Sockets","홈":"Sockets","요구 사항":"Requirements","요구사항":"Requirements",
  "레벨":"Level","힘":"Str","민첩":"Dex","지능":"Int","퀄리티":"Quality","품질":"Quality",
  "방어도":"Armour","회피":"Evasion Rating","회피도":"Evasion Rating","수호":"Ward",
  "에너지 보호막":"Energy Shield","막기":"Chance to Block","막기 확률":"Chance to Block",
  "물리 피해":"Physical Damage","원소 피해":"Elemental Damage","카오스 피해":"Chaos Damage",
  "혼돈 피해":"Chaos Damage","초당 공격":"Attacks per Second","치명타 확률":"Critical Strike Chance",
  "무기 범위":"Weapon Range","메모":"Note","노트":"Note",
  "초당 공격 횟수":"Attacks per Second","한계 사용 횟수":"Charges","지도 등급":"Map Tier","지도 티어":"Map Tier",
  "제한":"Limited to","반경":"Radius","회복":"Recovery","소모":"Consumes",
  "공격 속도":"Attacks per Second","무기 범위(칸)":"Weapon Range","실험실":"Lab",
  "무형성":"Intangibility"
};
const FRAME_CLASS = {
  "활":"Bows","지팡이":"Staves","전투 지팡이":"Warstaves","마법봉":"Wands","홀":"Sceptres",
  "룬 단검":"Rune Daggers","단검":"Daggers","발톱":"Claws",
  "한손 검":"One Hand Swords","찌르는 한손 검":"Thrusting One Hand Swords",
  "한손 도끼":"One Hand Axes","한손 철퇴":"One Hand Maces",
  "양손 검":"Two Hand Swords","양손 도끼":"Two Hand Axes","양손 철퇴":"Two Hand Maces",
  "낚싯대":"Fishing Rods","마나 플라스크":"Mana Flasks","생명력 플라스크":"Life Flasks",
  "유틸리티 플라스크":"Utility Flasks","복합 플라스크":"Hybrid Flasks",
  "주얼":"Jewels","심연 주얼":"Abyss Jewels","반지":"Rings","허리띠":"Belts","목걸이":"Amulets",
  "화살통":"Quivers","방패":"Shields","투구":"Helmets","장갑":"Gloves","장화":"Boots",
  "갑옷":"Body Armours","지도":"Maps","보조 젬":"Support Gems","스킬 젬":"Skill Gems"
};
const FRAME_VAL = {"일반":"Normal","마법":"Magic","희귀":"Rare","고유":"Unique",
  "젬":"Gem","화폐":"Currency","점술 카드":"Divination Card"};
const FRAME_FLAG = {
  "타락됨":"Corrupted","타락":"Corrupted","감정되지 않음":"Unidentified","미감정":"Unidentified",
  "거울 복제됨":"Mirrored","복제됨":"Mirrored","반사된":"Mirrored","분열됨":"Fractured","분열된 아이템":"Fractured Item","분할됨":"Split","분할된":"Split",
  "쉐이퍼 아이템":"Shaper Item","엘더 아이템":"Elder Item","정복자 아이템":"Warlord Item",
  "구원자 아이템":"Redeemer Item","성전사 아이템":"Crusader Item","사냥꾼 아이템":"Hunter Item",
  "합성 아이템":"Synthesised Item"
};
/* 한글 클라이언트도 이 표기는 영문 그대로 찍는다 -> 있는 그대로 통과 */
const SUFFIX_EN = new Set(["implicit","crafted","enchant","fractured","scourge",
  "synthesised","veiled","augmented","rune","desecrated","corrupted"]);
const SUFFIX = {"내재":"implicit","제작됨":"crafted","제작":"crafted","인챈트":"enchant",
  "각인":"enchant","분열":"fractured","합성":"synthesised","스컬지":"scourge"};
const BASE_PREFIX = [["상급 ","Superior "],["정교한 ","Superior "],
                     ["결합된 ","Synthesised "],["합성 ","Synthesised "]];
const SUFFIX_RE = /^(.*?)\s*\((.+?)\)\s*$/;

/* ---------- 게임 '고급 아이템 정보 표시' 문구 (역시 CSV에 없다) ---------- */
/* 촉매 장신구: "퀄리티 (저항 속성 부여): +20% (augmented)"
   게임은 '속성 부여', 한글 POB 는 '보정/속성 향상' 으로 쓴다. 둘 다 받는다. */
const QUAL_TAIL_RE = /\s*(?:속성 부여|속성 향상|보정|속성)$/;
const QUAL_HEAD = {
  "공격":"Attack","능력치":"Attribute","시전":"Caster","주문":"Caster","카오스":"Chaos",
  "냉기":"Cold","치명타":"Critical","방어":"Defence","원소 피해":"Elemental Damage",
  "원소":"Elemental","화염":"Fire","생명력 및 마나":"Life and Mana","생명력":"Life",
  "번개":"Lightning","마나":"Mana","물리 및 카오스 피해":"Physical and Chaos Damage",
  "물리 및 카오스":"Physical and Chaos","물리":"Physical","저항":"Resistance","속도":"Speed"
};
/* { 대가의 제작 접두어 속성 부여 "개량된" (등급: 2) — 피해, 원소 } */
const ADV_RE = /^\{\s*([\s\S]*?)\s*\}$/;
const ADV_HEAD_RE = /^(.*?속성(?:\s*부여)?)(?=\s|$)(?:\s*"([^"]*)")?(?:\s*\(([^)]*)\))?([\s\S]*)$/;
const ADV_KIND = {
  "고정":"Implicit","내재":"Implicit","비고정":"Explicit","접두어":"Prefix","접미어":"Suffix",
  "대가의 제작":"Master Crafted","제작됨":"Crafted","제작":"Crafted","인챈트":"Enchant",
  "각인":"Enchant","각인된":"Enchant","균열된":"Fractured","균열":"Fractured",
  "합성된":"Synthesised","합성":"Synthesised","스컬지":"Scourge","베일에 싸인":"Veiled",
  "베일":"Veiled","타락된":"Corrupted","타락":"Corrupted","신성모독":"Desecrated","룬":"Rune","분열된":"Fractured","분할된":"Split",
  // 엘드리치 고정 속성. "세계 포식자 고정 속성" = Eater of Worlds Implicit Modifier
  "세계 포식자":"Eater of Worlds","작열의 총주교":"Searing Exarch"
};
const ADV_TAG = {
  "피해":"Damage","원소":"Elemental","공격":"Attack","주문":"Caster","시전":"Caster",
  "방어력":"Defences","방어도":"Armour","회피":"Evasion","에너지 보호막":"Energy Shield",
  "카오스":"Chaos","저항":"Resistance","화염":"Fire","냉기":"Cold","번개":"Lightning",
  "물리":"Physical","생명력":"Life","마나":"Mana","속도":"Speed","치명타":"Critical",
  "능력치":"Attribute","소환수":"Minion","광역":"Area","발사체":"Projectile",
  "상태 이상":"Ailment","막기":"Block","회복":"Recovery","명중":"Accuracy","흡수":"Leech",
  "오라":"Aura","저주":"Curse","젬":"Gem","홈":"Socket","지속 시간":"Duration",
  "요구 사항":"Attribute","인챈트":"Enchantment","출현":"Drop"
};
const ADV_TIER_RE = /^\s*등급\s*:\s*(.+?)\s*$/;
const ADV_NOTE = {"변경이 불가능한 값":"Unscalable Value","합성됨":"Synthesised","분열됨":"Fractured"};
const ADV_PCT_RE = /^(\S+%)\s*(증가|감소)$/;
const DASH_RE = /\s+[—–]\s+/;     // 고급 정보 구분자
const DESC_RE = /^\(.*\)$/;       // 통째로 괄호인 설명 줄

/**
 * @param dict  { t, p, a } — build_data.py 가 만든 사전
 * @returns { line(raw), mod(ko), text(src) }
 */
export function createTranslator(dict) {
  const T = dict.t, P = dict.p, A = dict.a;

  /* 한 옵션 줄 → {en, alts} */
  function mod(ko){
    const p = P[ko];
    if (p !== undefined) return {en:p, alts:A[ko] || null};
    const cands = T[body(ko)];
    if (!cands) return null;
    let first = null; const alts = [];
    for (const [kt, et] of cands){
      const v = new Tmpl(kt).parse(ko);
      if (!v) continue;
      const en = new Tmpl(et).render(v);
      if (first === null) first = en;
      if (!alts.includes(en)) alts.push(en);
    }
    if (first === null) return null;
    return {en:first, alts: alts.length > 1 ? alts : null};
  }

  /* 통째로는 사전에 없지만 '앞절, 뒷절' 이 각각 있는 줄을 이어붙인다.
     한글 POB CSV 에 실제로 구멍이 있다 — 세계 포식자 고정 속성의
     '고유 적이 접근해 있는 동안, 주문 피해 {0}% 증가' 가 그런 경우다. */
    let CLAUSE = null;
  function buildClauses(){
    CLAUSE = Object.create(null);
    const add = (ko, en) => {
      const ik = ko.indexOf(", "), ie = en.indexOf(", ");
      if (ik > 0 && ie > 0 && CLAUSE[ko.slice(0, ik)] === undefined)
        CLAUSE[ko.slice(0, ik)] = en.slice(0, ie);
    };
    for (const v of Object.values(T)) for (const [ko, en] of v) add(ko, en);
    for (const ko in P) add(ko, P[ko]);
  }
  function clauseJoin(ko){
    const i = ko.indexOf(", ");
    if (i <= 0) return null;
    if (!CLAUSE) buildClauses();
    const ep = CLAUSE[ko.slice(0, i)];
    if (ep === undefined) return null;
    const r = mod(ko.slice(i + 2));
    return r ? ep + ", " + r.en : null;
  }

  /* 마법 아이템 이름 '접두 베이스 - 접미' 에서 베이스타입만 복원 */
  function compose(s){
    const core = s.split(" - ")[0].trim();
    const w = core.split(/\s+/);
    for (let i = 0; i < w.length; i++){
      const hit = P[w.slice(i).join(" ")];
      if (hit) return hit;
    }
    return null;
  }

  /* ---------- 고급 아이템 정보 ---------- */
  const term = (ko, table) => table[ko] || P[ko] || ko;

  /* 줄 끝 주석: '변경이 불가능한 값', '20% 증가' */
  function advNote(ko){
    ko = ko.trim();
    if (ADV_NOTE[ko]) return ADV_NOTE[ko];
    const m = ADV_PCT_RE.exec(ko);
    if (m) return `${m[1]} ${m[2] === "증가" ? "Increased" : "Reduced"}`;
    return mod(ko)?.en || ko;
  }

  /* '{ }' 안쪽: 접두어 속성 부여 "압도하는" (등급: 2) — 피해, 원소, 공격 */
  function advanced(inner){
    const m = ADV_HEAD_RE.exec(inner);
    if (!m) return inner;
    const [, kind, name, paren, rest] = m;
    // '대가의 제작 접두어 속성 부여' -> Master Crafted Prefix Modifier
    let words = kind.replace(QUAL_TAIL_RE, "").trim().split(/\s+/).filter(Boolean);
    const out = [];
    while (words.length){
      let hit = false;
      for (const n of [3,2,1]){                    // 긴 낱말('대가의 제작') 먼저
        const en = ADV_KIND[words.slice(0,n).join(" ")];
        if (en){ out.push(en); words = words.slice(n); hit = true; break; }
      }
      if (!hit) out.push(words.shift());
    }
    const parts = [out.concat("Modifier").join(" ")];
    if (name) parts.push(`"${term(name, {})}"`);
    if (paren){
      const t = ADV_TIER_RE.exec(paren);
      // (등급: 2) 는 Tier, (우수한) 같은 엘드리치 등급 이름은 사전에 있다
      parts.push(`(${t ? "Tier: " + t[1] : term(paren, {})})`);
    }
    for (const chunk of (rest || "").split(DASH_RE)){
      const c = chunk.trim();
      if (!c) continue;
      parts.push("— " + (c.includes(",") || ADV_TAG[c]
        ? c.split(",").map(t => term(t.trim(), ADV_TAG)).join(", ")
        : advNote(c)));
    }
    return parts.join(" ");
  }

  function line(raw){
    const s0 = stripColor(raw).trim();
    if (!s0) return {en:"", kind:"blank"};
    if (/^-{3,}$/.test(s0)) return {en:"--------", kind:"sep"};

    const adv = ADV_RE.exec(s0);
    if (adv) return {en:`{ ${advanced(adv[1])} }`, kind:"adv"};

    // 옵션 줄 뒤에 붙는 주석을 떼고 본문만 번역: "심연 홈 1개 — 변경이 불가능한 값"
    let s = s0, tail = "";
    const d = DESC_RE.test(s0) ? null : DASH_RE.exec(s0);
    if (d){ s = s0.slice(0, d.index).trim(); tail = " — " + advNote(s0.slice(d.index + d[0].length)); }

    const r = translateLine(s, raw);
    if (tail && r.kind !== "miss") r.en += tail;
    return r;
  }

  function translateLine(s, raw){
    if (s.includes(": ") || s.endsWith(":")){
      const i = s.indexOf(":");
      const k = s.slice(0, i).trim(), v = s.slice(i+1).trim();
      let ek = FRAME_KEY[k];
      if (!ek && P[k+":"]) ek = P[k+":"].replace(/:$/, "");
      if (!ek){                       // "퀄리티 (저항 속성 부여)" 처럼 괄호로 한정된 이름
        const q = SUFFIX_RE.exec(k);
        if (q && FRAME_KEY[q[1].trim()]){
          const qt = QUAL_HEAD[q[2].replace(QUAL_TAIL_RE, "").trim()];
          if (qt) ek = `${FRAME_KEY[q[1].trim()]} (${qt} Modifiers)`;
        }
      }
      if (ek){
        let ev = (ek === "Item Class" ? FRAME_CLASS[v] : null) || FRAME_VAL[v];
        if (!ev && v && !/^[\d.,%+\-\s]*$/.test(v)) ev = mod(v)?.en;
        return {en: v ? `${ek}: ${ev || v}` : `${ek}:`, kind:"frame"};
      }
    }
    if (FRAME_FLAG[s]) return {en:FRAME_FLAG[s], kind:"flag"};

    let core = s, sfx = null;
    const m = SUFFIX_RE.exec(s);
    if (m && (SUFFIX[m[2]] || SUFFIX_EN.has(m[2].toLowerCase()))){
      core = m[1]; sfx = SUFFIX[m[2]] || m[2].toLowerCase();
    }

    let r = mod(core);
    if (!r){
      for (const [kp, ep] of BASE_PREFIX){
        if (core.startsWith(kp)){
          const sub = mod(core.slice(kp.length));
          if (sub){ r = {en: ep + sub.en, alts:null}; break; }
        }
      }
    }
    const wrapSfx = e => sfx ? `${e} (${sfx})` : e;
    if (!r){
      const cj = clauseJoin(core);
      if (cj) return {en: wrapSfx(cj), kind:"part"};
    }
    if (!r){
      const b = compose(core);
      if (b) return {en:b, kind:"base"};
      // ("심연 주얼"만 심연의 홈에 장착할 수 있습니다) 같은 설명 줄.
      // POB 가 읽지 않는 문구라 번역해봐야 소용없고, 한글로 남겨두면
      // 결과만 지저분해진다. 아예 뺀다.
      if (DESC_RE.test(s)) return {en:"", kind:"drop"};
      return {en:raw, kind:"miss"};
    }
    const wrap = e => sfx ? `${e} (${sfx})` : e;
    return {
      en: wrap(r.en),
      kind: r.alts ? "amb" : "ok",
      alts: r.alts ? r.alts.map(wrap) : null
    };
  }

  const text = src => src.split("\n").map(line);

  return { line, mod, text };
}

export { body, stripColor, Tmpl };
