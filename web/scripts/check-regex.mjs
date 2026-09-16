/* 경로석 정규식 생성기 검증. 저장소에 테스트 틀이 없어 프레임워크 없이 돈다.

     npm run check:regex          (web/ 에서)
     node web/scripts/check-regex.mjs

   리그가 바뀌어 waystone_prices.py 의 AXES 구간을 손볼 때 이게 지켜 준다 — 구간 하나를
   한 자리 수로 바꾸면 band() 가 조용히 빈 문자열을 뱉고, 화면에는 등급만 든 정규식이
   복사된다. 그러면 창고의 경로석이 전부 걸린다. */
import { band, term, forQuery, MAX } from "../src/lib/waystone/regex.js";
import * as T from "../src/lib/tablet/regex.js";
import { KNOWN } from "../src/lib/tablet/known.js";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { gunzipSync } from "node:zlib";
import { globSync } from "node:fs";

let bad = 0;
const fail = (msg) => { console.log(`  틀림 — ${msg}`); bad++; };

// 1. 임계값마다 0~999 를 전부 넣어 '이 값 이상' 과 맞는지 본다.
//    정규식을 자릿수로 펼친 것이라 경계(9로 끝나는 값, 100 언저리)에서 틀리기 쉽다.
{
  let n = 0;
  for (let t = 10; t <= 999; t++) {
    const re = new RegExp(band(t));
    for (let v = 0; v <= 999; v++, n++)
      if (re.test(`+${v}%`) !== v >= t && bad < 5) fail(`band(${t}) 에 ${v} — ${band(t)}`);
  }
  console.log(`  band() ${n.toLocaleString()}쌍 대입${bad ? "" : " 통과"}`);
}

// 2. 올라가 있는 시세 파일의 축·구간이 전부 항을 만드는가. 빈 항은 조건 없는 검색이 된다.
{
  let doc = null;
  try {
    doc = JSON.parse(execFileSync("git", ["show", "origin/data:waystone-prices.json"],
      { cwd: new URL("../..", import.meta.url).pathname, encoding: "utf8" }));
  } catch {
    console.log("  시세 파일 없음 — 축·구간 확인을 건너뛴다 (git fetch origin data)");
  }
  if (doc) {
    let n = 0;
    for (const ax of doc.axes || [])
      for (const t of doc.tiers || [])
        for (const b of ax.bands?.[String(t)] || []) {
          n++;
          if (!term(ax.id, b)) fail(`${t}등급 ${ax.label} ${b} — 빈 항`);
        }
    for (const c of doc.combos || []) {
      n++;
      const s = forQuery(c.tier, c.parts);
      if (c.parts.some(([a, v]) => !term(a, v))) fail(`${c.key} — 빈 항`);
      if (s.length > MAX) fail(`${c.key} — ${s.length}자 (한도 ${MAX})`);
    }
    console.log(`  시세 파일의 ${n}자리 전부 항을 만든다${bad ? "" : " ·  250자 넘는 것 없음"}`);
  }
}

// 3. 가장 긴 것이 얼마나 되는지 적어 둔다 — 한도에 얼마나 붙었는지 사람이 보게.
{
  const all = [];
  for (const a of ["eff", "rare", "iir", "pack", "bonus"])
    for (const b of [30, 45, 75, 86, 120, 160]) all.push(forQuery(16, [[a, b], ["pack", 25]]));
  const longest = all.sort((x, y) => y.length - x.length)[0];
  console.log(`  가장 긴 조합 ${longest.length}자 / ${MAX}자`);
}

// ── 서판 ────────────────────────────────────────────────────────────────
//
// 조각은 게임 글월에 묶여 있다. 시즌이 바뀌어 문구가 달라지거나 옵션이 늘면 조각이
// 조용히 다른 옵션까지 잡는다 — 값은 멀쩡한데 검색만 틀린다. 그래서 여기서 지킨다.
console.log("\n서판");

// 5. 카탈로그의 문구마다 조각이 있는가, 그 조각이 남의 옵션까지 잡지는 않는가
//
//    조각은 두 곳에서 온다. known.js 의 손질 표(대부분 서판 **이름 줄**의 접사 이름을
//    노린다)와, 표에 없을 때 문구에서 뽑는 생성기다. 그래서 '자기 문구에 맞는가' 는
//    생성기 쪽에만 물을 수 있다 — 이름 줄 조각은 옵션 문구에 아예 없다.
{
  const root = new URL("../..", import.meta.url).pathname;
  const files = globSync("web/public/data/tablet-catalog-*.json.gz", { cwd: root });
  if (!files.length) {
    console.log("  카탈로그가 없다 — 서판 확인을 건너뛴다");
  } else {
    const cat = JSON.parse(gunzipSync(readFileSync(`${root}/${files[0]}`)).toString());
    const all = [...new Set(cat.mods.map((m) => m.text))];
    const at = (t, d) => t.replace(/#/g, d).replace(/\s+/g, " ").trim();
    const t0 = performance.now();
    const frag = new Map(all.map((t) => [t, T.compact(t, all)]));
    const fromTable = all.filter((t) => KNOWN.has(t)).length;
    console.log(`  문구 ${all.length}개 · 표에서 ${fromTable} · 생성기가 ${all.length - fromTable}`
      + ` · ${(performance.now() - t0).toFixed(0)}ms`);

    // 조각이 겹치면 통합 정규식에서 한 항이 남의 옵션 노릇을 한다
    const seen = new Map();
    for (const [t, f] of frag) {
      if (seen.has(f)) fail(`조각 '${f}' 가 둘이다 — '${t}' 와 '${seen.get(f)}'`);
      seen.set(f, t);
    }

    for (const [t, f] of frag) {
      const rx = new RegExp(f, "u");
      // 생성기가 만든 것은 자기 문구에 맞아야 한다(한·두·세 자리 모두)
      if (!KNOWN.has(t))
        for (const d of ["7", "17", "170"])
          if (!rx.test(at(t, d))) fail(`${t} — 생성 조각 ${f} 가 자기 문구(${d})에 안 맞는다`);
      // 어느 쪽이든 남의 문구를 잡으면 안 된다
      const caught = all.filter((o) => o !== t && ["7", "17", "170"].some((d) => rx.test(at(o, d))));
      if (caught.length) fail(`${t} — 조각 ${f} 가 '${caught[0]}' 까지 잡는다`);
    }
    // 서판에는 옵션 말고도 늘 붙어 있는 줄이 있다. 조각이 여기 걸리면 그 종류가 통째로
    // 걸린다 — 통합 정규식은 `|` 로 잇기 때문에 한 항이 표 전체를 무의미하게 만든다.
    const ALWAYS = [
      ...cat.bases.map((b) => b.type),
      "아이템 종류: 서판", "아이템 희귀도: 마법", "잔여 사용 횟수: 10",
      "지도 장치에 사용하여 인근 지도에 영향을 줍니다", "아이템 레벨: 79",
    ];
    for (const [t, f] of frag) {
      const rx = new RegExp(f, "u");
      const on = ALWAYS.filter((line) => rx.test(line));
      if (on.length) fail(`${t} — 조각 ${f} 가 늘 붙는 줄('${on[0]}')에 걸린다`);
    }

    const lens = [...frag.values()].map((f) => f.length).sort((a, b) => a - b);
    console.log(`  길이 중앙 ${lens[lens.length >> 1]}자 · 최대 ${lens.at(-1)}자`
      + `${bad ? "" : " · 겹침 없음 · 늘 붙는 줄에 안 걸림"}`);

    // 6. 최악의 경우(기준 0, 옵션 전부)에도 조각이 한도를 안 넘는가
    const terms = [...new Set(cat.mods.map((m) => T.hitTerm(m, all)))];
    const parts = T.chunk(terms);
    const over = parts.filter((p) => p.length > T.MAX);
    console.log(`  통합 ${terms.length}항 → ${parts.length}조각 · 가장 긴 ${Math.max(...parts.map((p) => p.length))}자`);
    if (over.length) fail(`${over.length}조각이 ${T.MAX}자를 넘는다`);

  }
}

console.log(bad ? `\n어긋남 ${bad}건` : "\n통과");
process.exit(bad ? 1 : 0);
