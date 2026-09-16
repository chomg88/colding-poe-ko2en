/* 경로석 정규식 생성기 검증. 저장소에 테스트 틀이 없어 프레임워크 없이 돈다.

     npm run check:regex          (web/ 에서)
     node web/scripts/check-regex.mjs

   리그가 바뀌어 waystone_prices.py 의 AXES 구간을 손볼 때 이게 지켜 준다 — 구간 하나를
   한 자리 수로 바꾸면 band() 가 조용히 빈 문자열을 뱉고, 화면에는 등급만 든 정규식이
   복사된다. 그러면 창고의 경로석이 전부 걸린다. */
import { band, term, forQuery, MAX } from "../src/lib/waystone/regex.js";
import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";

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

console.log(bad ? `\n어긋남 ${bad}건` : "\n통과");
process.exit(bad ? 1 : 0);
