/* 서판 옵션 → 게임 창고 검색창에 넣을 정규식.

   경로석(web/src/lib/waystone/regex.js)과 하는 일은 같지만 방법이 다르다. 경로석은 값이
   아이템에 찍힌 수치에서 나서 '몬스터 효율:' 같은 앞자리 몇 글자면 됐다. 서판은 값이
   옵션 문구에서 나는데, 그 문구가 '지도에서 발견하는 복제된 영토 파편의 중첩 개수 #% 증가'
   처럼 길다. 통째로 넣으면 검색창 250자가 금방 찬다.

   그래서 **그 옵션을 다른 옵션과 갈라 주는 가장 짧은 조각**을 찾는다. 카탈로그로 재 보니
   서로 다른 문구 86개가 중앙 2자·최대 5자로 갈렸다(`는.*아`, `리.*규`, `^몬`).

   그리는 일과 나눠 둔 까닭은 DOM 없이 불러 검증할 수 있어야 해서다 —
   web/scripts/check-regex.mjs. */

import { KNOWN } from "./known.js";

/** 정규식에서 뜻을 갖는 글자를 막는다. */
export const esc = (s) => String(s).replace(/[\\^$.*+?()[\]{}|]/g, "\\$&");

/* 낱말 후보를 만들 때 지우는 말. 거의 모든 문구에 들어 있어 갈라 주지 못한다.
   다만 이 목록만 믿지는 않는다 — '확률' 과 '추가' 를 지우면 '에센스가 등장할 확률' 과
   '에센스 1개 추가 등장' 이 같아져 버린다. 그래서 아래 candidates() 가 원문 위를 창으로
   훑는 단계를 따로 둔다. */
const FILLER = /지도 내|지역 내|지도에서|지역에서|지도에|지역에|의식 제단|헌정품|공물 점수|확률|증가|감소|추가|허용/g;

/** 문구 조각 → 정규식. 공백은 `.` 한 글자로, 숫자 자리(\0)는 `\d+` 로. */
const win = (s) => [...s].map((c) => (c === " " ? "." : c === "\0" ? "\\d+" : esc(c))).join("");

/** 조각 후보를 짧은 것부터. 셋으로 나뉜다. */
function candidates(text) {
  const out = [];

  // 1. 낱말 기반 — 불용어를 지우고 남은 낱말의 첫·끝 글자를 엮는다. 제일 짧게 나온다.
  const words = text.replace(/#/g, " # ").replace(FILLER, " ")
    .split(/\s+/).filter((w) => /[가-힣A-Za-z]/.test(w));
  for (let i = 0; i < words.length - 1; i++) {
    const a = [...words[i]], b = [...words[i + 1]];
    out.push(`${esc(a.at(-1))}.*${esc(b[0])}`, `${esc(a.at(-1))}.${esc(b[0])}`);
  }
  for (const w of words) {
    const c = [...w];
    if (c.length === 1) out.push(esc(c[0]));
    else out.push(`${esc(c.at(-2))}.${esc(c.at(-1))}`,
                  `${esc(c[0])}.*${esc(c.at(-1))}`,
                  esc(c.slice(0, 3).join("")));
  }

  // 2. 문구 위를 창으로 훑기. 불용어가 갈라 주는 자리(확률 / 추가)를 여기서 건진다.
  //    숫자 자리는 \d+ 다 — \d 한 자리로 두면 '효율 15%' 같은 두 자리 값에서 떨어진다.
  const s = text.replace(/#/g, "\0").replace(/\s+/g, " ").trim();
  for (let n = 2; n < 12; n++)
    for (let i = 0; i + n <= s.length; i++) out.push(win(s.slice(i, i + n)));

  // 3. 줄 처음에 붙이기. 한 문구가 다른 문구에 통째로 들어 있을 때만 갈린다 —
  //    '몬스터의 효율' ⊂ '지도 내 몬스터의 효율'. 실제로 쓰이는 것은 '^몬' 하나다.
  for (let n = 1; n < 14 && n <= s.length; n++) out.push("^" + win(s.slice(0, n)));

  return [...new Set(out)].sort((a, b) => a.length - b.length);
}

/* 서판이면 늘 붙어 있는 줄. 조각이 여기 걸리면 그 서판이 통째로 걸린다 — 통합 정규식은
   `|` 로 잇기 때문에 그런 항 하나가 표 전체를 무의미하게 만든다.

   실제로 밟았다. '지도에서 발견하는 아이템 희귀도 #% 증가' 의 조각으로 '템.희' 를 골랐는데,
   마법 아이템이면 늘 있는 '아이템 희귀도: 마법' 에 걸렸다. 옵션 문구끼리만 겨루면 안 보인다.

   서판 종류 이름(의식 서판 …)은 여기 없다 — 카탈로그에서 와야 해서 검증 쪽에서 본다. */
const ALWAYS = [
  "아이템 종류: 서판", "아이템 희귀도: 마법", "아이템 희귀도: 일반", "잔여 사용 횟수: 10",
  "지도 장치에 사용하여 인근 지도에 영향을 줍니다", "아이템 레벨: 79",
];

/** 맞춰 볼 실제 글월. 숫자 자리에 한·두·세 자리를 다 넣어 본다 — 하나라도 떨어지면 버린다. */
const targets = (text) =>
  ["7", "17", "170"].map((d) => text.replace(/#/g, d).replace(/\s+/g, " ").trim());

/* 조각이 뜻을 가지려면 알맹이가 최소 두 글자는 있어야 한다.

   유일성은 '다른 옵션 문구' 하고만 겨룬다. 그런데 게임 창고에서 맞춰 보는 것은 아이템
   전체다 — 서판 이름('으스스한 탐험'), 종류, 잔여 사용 횟수, 설명 글까지 들어 있다.
   그래서 '를' · '피' · '더' 같은 한 글자는 옵션끼리는 갈려도 엉뚱한 줄에 걸린다. 통합
   정규식은 이것들을 `|` 로 잇기 때문에 헐렁한 항 하나가 창고를 통째로 물들인다.

   두 글자를 요구하면 '^몬' 이 '^몬스' 가 되는 식으로 한두 글자 길어질 뿐이다. */
const SOLID = (c) => (c.match(/[가-힣A-Za-z0-9]/g) || []).length >= 2;

/** 이 문구를 others 와 갈라 주는 가장 짧은 조각. 못 찾으면 문구를 통째로 쓴다.

    others 는 '겨루는 상대' 다. 행 버튼은 같은 서판 종류의 옵션끼리, 통합 정규식은 종류를
    안 가리므로 전체 문구끼리 겨룬다 — 그래서 두 벌을 따로 만든다. */
export function compact(text, others) {
  // 손으로 맞춘 표가 먼저다(known.js). 생성기는 옵션 문구만 보므로 존재형과 범위형이 같은
  // 글자로 찍히는 자리를 못 가르고, 그 자리는 표가 접사 이름으로 넘어가 있다.
  const known = KNOWN.get(text);
  if (known) return known[0];

  const mine = targets(text);
  const foes = others.filter((o) => o !== text).flatMap(targets).concat(ALWAYS);
  for (const c of candidates(text)) {
    if (!SOLID(c)) continue;
    let rx;
    try { rx = new RegExp(c, "u"); } catch { continue; }
    if (!mine.every((x) => rx.test(x))) continue;
    if (foes.some((x) => rx.test(x))) continue;
    return c;
  }
  return win(text.replace(/#/g, "\0").replace(/\s+/g, " ").trim());
}

/** 숫자 뒤에 붙는 단위. 카탈로그 문구가 이미 갖고 있으므로 짐작하지 않는다.

    아는 단위만 집는다. '다음 공백까지' 로 하면 '#%씩,' · '#마리가' 처럼 뒤엣말을 물고
    들어와, 정규식이 그 조사까지 맞아야 하는 것이 된다. 화면의 수치 칩도 이 함수를 쓴다. */
export function unit(text) {
  const m = /#\s*(%|초|개|회|마리|명)/.exec(text);
  return m ? m[1] : "";
}

/** 행 버튼 — 서판 종류와 옵션만. 수치는 넣지 않는다. */
export function rowTerm(mod, others) {
  return `"${esc(mod.base)}" "${compact(mod.text, others)}"`;
}

/** 통합 정규식에 들어갈 한 항 — 조각 그대로다.

    수치는 걸지 않는다. 그 옵션이 붙었는지만 보면 되고, 무엇을 담을지는 표의 기준 필터가
    이미 정한다. 수치를 걸려면 조각이 옵션 줄에 있어야 하는데, 좋은 조각은 대부분 이름 줄에
    있어서(known.js) 둘을 `.*` 로 이으면 검색이 줄 단위일 때 성립하지 않는다. */
export function hitTerm(mod, others) {
  return compact(mod.text, others);
}

/** 검색창이 받는 길이. */
export const MAX = 250;

/* 자를 때는 한도에 딱 붙이지 않는다. 게임 쪽 셈이 한 글자라도 다르면(따옴표를 세는지,
   공백을 어떻게 세는지) 뒤가 잘려 나가는데, 잘린 정규식은 오류가 아니라 '조용히 다른 것을
   잡는' 쪽으로 망가진다. */
const BUDGET = 240;

/** 항들을 `|` 로 이으면서 한도를 넘기 전에 자른다. → ["...", "..."] */
export function chunk(terms, max = BUDGET) {
  const out = [];
  let cur = "";
  for (const t of terms.filter(Boolean)) {
    const next = cur ? `${cur}|${t}` : t;
    if (cur && next.length > max) { out.push(cur); cur = t; } else cur = next;
  }
  if (cur) out.push(cur);
  return out;
}
