import { createTranslator } from "./engine.js";

const OK_KINDS = new Set(["ok", "frame", "flag", "base", "adv", "part"]);
const TAGS = {
  miss: ["없음", null],
  base: ["베이스만", "마법 아이템 이름에서 베이스타입만 복원했습니다. 접사는 아래 옵션 줄에 그대로 있습니다."],
  part: ["이어붙임", "이 줄이 원본 CSV 에 통째로는 없어서, 앞절과 뒷절을 각각 찾아 이어붙였습니다."],
};

const SAMPLE = [
  "아이템 종류: 허리띠", "아이템 희귀도: 희귀", "크라켄의 가죽끈", "명계의 조임쇠", "--------",
  "퀄리티 (저항 속성 부여): +20% (augmented)", "--------",
  "요구사항:", "레벨: 67", "--------", "홈: A ", "--------", "아이템 레벨: 85", "--------",
  "{ 고정 속성 부여 }", "심연 홈 1개 — 변경이 불가능한 값",
  '("심연 주얼"만 심연의 홈에 장착할 수 있습니다)', "--------",
  '{ 접두어 속성 부여 "압도하는" (등급: 2) — 피해, 원소, 공격 }',
  "공격 스킬의 원소 피해 38(37-42)% 증가",
  '{ 접두어 속성 부여 "가로 덧댄" (등급: 6) — 방어력, 방어도 }',
  "방어도 +55(36-60)",
  '{ 대가의 제작 접두어 속성 부여 "개량된" — 피해 }',
  "피해 17(15-17)% 증가",
  '{ 접미어 속성 부여 "- 바메스" (등급: 1) — 카오스, 저항  — 20% 증가 }',
  "카오스 저항 +32(31-35)%", "--------", "엘더 아이템",
].join("\n");

/** .gz 를 받아 푼다. 호스트가 Content-Encoding: gzip 을 붙이면 브라우저가
    이미 풀어서 주므로, gzip 매직바이트로 판별해 이중 해제를 피한다. */
async function grab(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url} — HTTP ${res.status}`);
  const buf = new Uint8Array(await res.arrayBuffer());
  const gz = buf[0] === 0x1f && buf[1] === 0x8b;
  const text = gz
    ? await new Response(new Blob([buf]).stream().pipeThrough(new DecompressionStream("gzip"))).text()
    : new TextDecoder().decode(buf);
  return JSON.parse(text);
}

export function mount(root, { core, names }) {
  const $ = (s) => root.querySelector(s);
  const $in = $("[data-in]"), $out = $("[data-out]"), $tally = $("[data-tally]");
  const $veil = $("[data-veil]"), $app = root.querySelectorAll("[data-app]");
  const override = new Map();
  let tr = null;

  function render() {
    const src = $in.value;
    $out.textContent = "";
    if (!src.trim()) {
      const d = document.createElement("div");
      d.className = "empty";
      d.textContent = "왼쪽에 한글 아이템 텍스트를 붙여넣으면 여기에 영문이 나옵니다.";
      $out.append(d);
      $tally.textContent = "";
      return;
    }
    const lines = tr.text(src);
    let ok = 0, amb = 0, miss = 0, total = 0;
    const frag = document.createDocumentFragment();

    lines.forEach((r, i) => {
      if (r.kind === "drop") return;
      if (r.kind !== "sep" && r.kind !== "blank") total++;
      if (OK_KINDS.has(r.kind)) ok++;
      else if (r.kind === "amb") { amb++; ok++; }
      else if (r.kind === "miss") miss++;

      const row = document.createElement("div");
      row.className = "ln " + r.kind;
      const txt = document.createElement("span");
      txt.className = "txt";
      txt.textContent = override.get(i) ?? r.en;
      row.append(txt);

      const t = TAGS[r.kind];
      if (t) {
        const el = document.createElement("span");
        el.className = "tag"; el.textContent = t[0];
        if (t[1]) el.title = t[1];
        row.append(el);
      }
      if (r.kind === "amb") {
        const el = document.createElement("span");
        el.className = "tag"; el.textContent = r.alts.length + "안";
        row.append(el);
        row.tabIndex = 0;
        row.setAttribute("role", "button");
        row.setAttribute("aria-label", "다른 후보 보기");
        const toggle = () => {
          if (row.nextElementSibling?.classList.contains("alts")) {
            row.nextElementSibling.remove();
            return;
          }
          const box = document.createElement("div");
          box.className = "alts";
          const l = document.createElement("span");
          l.className = "lbl"; l.textContent = "같은 한글에 대응하는 다른 영문";
          box.append(l);
          r.alts.forEach((a) => {
            const b = document.createElement("button");
            b.type = "button"; b.textContent = a;
            b.onclick = (e) => { e.stopPropagation(); override.set(i, a); render(); };
            box.append(b);
          });
          row.after(box);
        };
        row.onclick = toggle;
        row.onkeydown = (e) => {
          if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); }
        };
      }
      frag.append(row);
    });

    $out.append(frag);
    const pct = total ? Math.round((ok / total) * 100) : 0;
    $tally.innerHTML =
      `매칭 <b>${pct}%</b>` +
      (amb ? ` · 후보 여럿 <b>${amb}</b>` : "") +
      (miss ? ` · 미매칭 <b>${miss}</b>` : "");
  }

  const plain = () =>
    $in.value.split("\n")
      .map((src, i) => {
        const ov = override.get(i);
        if (ov !== undefined) return ov;
        const r = tr.line(src);
        return r.kind === "drop" ? null : r.en;
      })
      .filter((l) => l !== null)
      .join("\n");

  let timer;
  $in.addEventListener("input", () => {
    override.clear();
    clearTimeout(timer);
    timer = setTimeout(render, 90);
  });
  $("[data-copy]").onclick = async (e) => {
    const b = e.currentTarget;
    try {
      await navigator.clipboard.writeText(plain());
      b.textContent = "복사됨";
    } catch { b.textContent = "복사 실패 — 직접 선택하세요"; }
    setTimeout(() => (b.textContent = "복사"), 1600);
  };
  $("[data-clear]").onclick = () => { $in.value = ""; override.clear(); render(); $in.focus(); };
  $("[data-sample]").onclick = () => { $in.value = SAMPLE; override.clear(); render(); };

  (async () => {
    try {
      const dict = await grab(core);
      tr = createTranslator(dict);
      $veil.remove();
      $app.forEach((el) => (el.hidden = false));
      render();
      $in.focus();
      try {
        Object.assign(dict.p, await grab(names));
        if ($in.value.trim()) render();
      } catch (e) {
        console.warn("이름 사전 생략:", e.message);
      }
    } catch (e) {
      $veil.querySelector("[data-note]").textContent = "사전을 불러오지 못했습니다 — " + e.message;
      $veil.querySelector(".bar")?.remove();
    }
  })();
}
