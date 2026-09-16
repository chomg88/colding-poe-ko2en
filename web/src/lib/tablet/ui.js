/* 서판 시세 화면.

   카탈로그(무엇을 물어봤나)는 빌드에 박힌 해시 파일이고, 값은 운영자 PC 의 수집기가
   GitHub data 브랜치에 올리는 tablet-prices.json 이다. 둘을 구간 키로 잇는다.

   값은 사이트 배포와 따로 움직이고, 운영자 PC 가 꺼지면 멈춘다. 그래서 마지막 갱신
   시각을 늘 보여 주고, 오래되면 표 위에 경고를 띄운다(data-warn / data-bad 시간). */

import { rowTerm, hitTerm, chunk, unit as unitOf } from "./regex.js";

const TRADE = "https://poe.kakaogames.com/trade2/search/poe2";
const REFRESH_MS = 5 * 60 * 1000;
const STORE = "colding-tablet";
const DEF = { base: "", affix: "all", cur: "ex", th: 30, only: false, q: "" };

/** .gz 면 풀고 아니면 그대로. 호스트가 Content-Encoding: gzip 을 붙이면 브라우저가
    이미 풀어서 주므로 매직바이트로 판별한다(아이템 변환기와 같다). */
async function grab(url, init) {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const buf = new Uint8Array(await res.arrayBuffer());
  const gz = buf[0] === 0x1f && buf[1] === 0x8b;
  const text = gz
    ? await new Response(new Blob([buf]).stream().pipeThrough(new DecompressionStream("gzip"))).text()
    : new TextDecoder().decode(buf);
  return JSON.parse(text);
}

function loadPrefs() {
  try { return { ...DEF, ...JSON.parse(localStorage.getItem(STORE) || "{}") }; }
  catch { return { ...DEF }; }
}
function savePrefs(S) {
  try { localStorage.setItem(STORE, JSON.stringify(S)); } catch { /* 저장 못 해도 화면은 돈다 */ }
}

const esc = (s) => String(s ?? "").replace(/[&<>"]/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const now = () => Date.now() / 1000;

function ago(sec) {
  if (sec < 90) return "방금";
  if (sec < 3600) return `${Math.round(sec / 60)}분`;
  if (sec < 172800) return `${Math.round(sec / 3600)}시간`;
  return `${Math.round(sec / 86400)}일`;
}

export function mount(el) {
  const $ = (s) => el.querySelector(s);
  const warnH = Number(el.dataset.warn) || 3;
  const badH = Number(el.dataset.bad) || 24;
  const S = loadPrefs();
  let C = null;       // 카탈로그
  let P = null;       // 시세
  let perr = "";      // 시세 파일을 못 받은 사유
  let J = [];         // 카탈로그 × 시세

  /* 칸에는 숫자만 둔다. 단위는 열 머리([data-unit])에 한 번 — 칸마다 붙이면 수치 칩
     셋이 옵션 칸을 밀어 문구가 세 줄로 접힌다. */
  const inDiv = () => S.cur === "div" && !!P?.rates?.divine;
  function money(ex) {
    if (ex == null) return "-";
    if (inDiv()) {
      const d = ex / P.rates.divine;
      return d >= 10 ? d.toFixed(0) : d >= 1 ? d.toFixed(1) : d.toFixed(2);
    }
    return ex >= 100 ? Math.round(ex).toLocaleString() : ex >= 10 ? ex.toFixed(0) : ex.toFixed(1);
  }
  const unitName = () => (inDiv() ? "디바인" : "엑잘");

  /* 옵션을 갈라 주는 짧은 조각은 카탈로그가 정해지면 바뀌지 않는다. 문구 86개에 68ms 라
     한 번 계산해 두고 쓴다 — 표를 다시 그릴 때마다 하면 필터를 만질 때마다 멈칫한다.

     두 벌인 까닭: 행 버튼은 서판 종류를 같이 박으므로 같은 종류의 옵션끼리만 갈리면 되고
     (그래서 더 짧다), 통합 정규식은 창고를 통째로 훑느라 종류를 안 가려 전체에서 갈려야 한다. */
  let RX = null;
  function fragments() {
    if (RX) return RX;
    const all = [...new Set(C.mods.map((m) => m.text))];
    const byBase = new Map();
    for (const m of C.mods) byBase.set(m.base, [...(byBase.get(m.base) ?? []), m.text]);
    RX = { row: new Map(), all };
    for (const m of C.mods) {
      const k = `${m.base}\u0000${m.text}`;
      if (!RX.row.has(k)) RX.row.set(k, rowTerm(m, byBase.get(m.base)));
    }
    return RX;
  }
  const rowRx = (m) => fragments().row.get(`${m.base}\u0000${m.text}`) || "";

  /** 통합 정규식에 넣을 항. 수치는 안 건다 — 그 옵션이 붙었는지만 보면 되고, 무엇을
      담을지는 표에 걸린 기준 필터가 이미 정한다. */
  const hitRx = (r) => hitTerm(r.m, fragments().all);

  function join() {
    const b = P?.b || {};
    J = C.mods.map((m) => ({
      m,
      unit: unitOf(m.text),
      bands: m.keys.map((k, i) => {
        const r = b[k];
        return {
          t: m.bands.length ? m.bands[i] : null,
          at: r?.[0] ?? null, total: r?.[1] ?? null, n: r?.[2] ?? null,
          min: r?.[3] ?? null, med: r?.[4] ?? null, qid: r?.[5] || "", err: r?.[6] || "",
        };
      }),
    }));
  }

  async function loadPrices() {
    try {
      // raw.githubusercontent 는 5분쯤 캐시한다. 분 단위로 주소를 바꿔 그보다 오래 묵지 않게.
      const url = `${el.dataset.prices}?v=${Math.floor(Date.now() / 60000)}`;
      P = await grab(url, { cache: "no-store" });
      perr = "";
    } catch (e) {
      perr = e.message;       // 전에 받은 값이 있으면 그대로 두고 경고만 띄운다
    }
    join();
  }

  function status() {
    const alert = $("[data-alert]");
    let level = "", msg = "";
    if (!P) {
      level = "bad";
      msg = `시세 파일을 받지 못했습니다(${perr}). 옵션 목록만 보여 드립니다 — 잠시 뒤 다시 열어 주세요.`;
    } else if (P.league !== C.league) {
      level = "bad";
      msg = `표의 값은 ${P.league} 리그 기준입니다. 이번 리그(${C.league}) 시세는 아직 모이는 중입니다.`;
    } else {
      const h = (now() - P.updatedAt) / 3600;
      if (h >= badH) {
        level = "bad";
        msg = `수집이 ${ago(now() - P.updatedAt)} 전에 멈췄습니다. 값이 지금 시세와 많이 다를 수 있으니, `
          + `사고팔기 전에 거래소 링크로 직접 확인하세요.`;
      } else if (h >= warnH) {
        level = "warn";
        msg = `마지막 갱신이 ${ago(now() - P.updatedAt)} 전입니다. 수집이 잠시 멈춘 것 같습니다 — 값이 조금 늦을 수 있습니다.`;
      }
    }
    alert.hidden = !level;
    alert.className = `tb-alert ${level}`;
    alert.textContent = msg;

    const box = $("[data-status]");
    if (!P) { box.innerHTML = `<span>${esc(C.league)}</span><span>시세 없음</span>`; return; }
    const p = P.progress || {};
    const rep = p.rep || [0, 0], deep = p.deep || [0, 0];
    box.innerHTML = [
      `<span>${esc(P.league)}</span>`,
      `<span>마지막 갱신 <b>${ago(now() - P.updatedAt)}</b> 전</span>`,
      `<span title="옵션마다 가장 낮은 수치로 한 번씩">대표 <b>${rep[0]}/${rep[1]}</b></span>`,
      `<span title="대표 중앙값이 ${P.deepMin ?? 30}엑잘 이상인 옵션의 나머지 수치">정밀 <b>${deep[0]}/${deep[1]}</b></span>`,
      P.rates?.divine ? `<span>1 디바인 = <b>${Math.round(P.rates.divine)}</b> 엑잘</span>` : "",
      perr ? `<span class="tb-err">새 값을 못 받음 — ${esc(perr)}</span>` : "",
    ].join("");
  }

  function controls() {
    $('[data-seg="base"]').innerHTML = ["", ...C.bases.map((b) => b.type)].map((b) =>
      `<button type="button" data-v="${esc(b)}">${b ? esc(b.replace(" 서판", "")) : "전체"}</button>`).join("");
    for (const seg of el.querySelectorAll("[data-seg]")) {
      const key = seg.dataset.seg;
      for (const b of seg.children) b.setAttribute("aria-pressed", String(b.dataset.v === S[key]));
    }
    $("[data-th]").value = S.th;
    $("[data-only]").checked = S.only;
    $("[data-q]").value = S.q;
  }

  /* 대표가 싼 옵션은 나머지 수치를 모으지 않는다(수집기 deepMin). 그 칸은 '대기' 가
     아니라 '안 봄' 이다 — 기다려도 값이 오지 않는다. */
  const skipped = (r) => r.bands[0].med != null && r.bands[0].med < (P?.deepMin ?? 30);

  function chip(r, b, i) {
    if (b.t == null) return "";
    const lab = `${b.t}${r.unit}+`;
    if (b.err) return `<span class="tb-chip err" title="${esc(b.err)}">${lab} 오류</span>`;
    if (!b.at && i > 0 && skipped(r)) {
      return `<span class="tb-chip off" title="대표 중앙값이 ${P.deepMin ?? 30}엑잘 미만이라 수치별 시세는 모으지 않습니다">${lab} <b>-</b></span>`;
    }
    const v = b.at ? (b.med != null ? money(b.med) : "매물 없음") : "대기";
    const hot = b.med != null && b.med >= S.th ? " hot" : "";
    const tip = b.at ? `매물 ${b.total ?? "-"} · 최저 ${money(b.min)} ${unitName()} · ${ago(now() - b.at)} 전` : "아직 안 봄";
    return b.qid
      ? `<a class="tb-chip${hot}" href="${TRADE}/${encodeURIComponent(P.league)}/${esc(b.qid)}" target="_blank" rel="noopener" title="${esc(tip)}">${lab} <b>${v}</b></a>`
      : `<span class="tb-chip${hot}" title="${esc(tip)}">${lab} <b>${v}</b></span>`;
  }

  function row(r, i) {
    const m = r.m, b0 = r.bands[0];
    const hot = b0.med != null && b0.med >= S.th;
    const text = m.range ? m.text.replace("#", `(${m.range.min}–${m.range.max})`) : m.text;
    const stale = b0.at && now() - b0.at > badH * 3600;
    const chips = m.bands.length ? r.bands.map((b, i) => chip(r, b, i)).join("") : `<span class="tb-dim">존재형</span>`;
    const med = b0.err ? `<span class="tb-chip err" title="${esc(b0.err)}">오류</span>`
      : b0.at ? `<span class="tb-med${hot ? " hot" : ""}">${b0.med != null ? money(b0.med) : "매물 없음"}</span>`
      : `<span class="tb-dim">대기</span>`;
    const link = b0.qid && P
      ? `<a class="tb-go" href="${TRADE}/${encodeURIComponent(P.league)}/${esc(b0.qid)}" target="_blank" rel="noopener">거래소</a>` : "";
    // 행 버튼은 수치를 넣지 않는다 — '이 옵션이 붙은 게 있나' 를 본다. 수치까지 걸고 싶으면
    // 표 위의 통합 정규식이 기준을 넘는 구간으로 만들어 준다.
    const rx = rowRx(m);
    const rxBtn = rx
      ? `<button type="button" class="tb-rx" data-rx="${esc(rx)}"
           title="${esc(`창고 검색식을 복사합니다 — ${rx}`)}">정규식</button>` : "";
    return `<tr class="${hot ? "hot" : ""}${stale ? " stale" : ""}">
      <td class="num tb-dim">${i + 1}</td>
      ${S.base ? "" : `<td class="tb-base">${esc(m.base.replace(" 서판", ""))}</td>`}
      <td><span class="tb-aff ${m.affix}">${m.affix === "prefix" ? "접두" : "접미"}</span></td>
      <td class="tb-mod">${esc(text)}${m.sign < 0 ? ` <span class="tb-dim" title="거래소에는 '증가' 옵션의 음수로 올라 있어 그렇게 검색합니다">(음수 검색)</span>` : ""}</td>
      <td class="num tb-dim">${b0.total != null ? b0.total.toLocaleString() : ""}</td>
      <td class="num">${b0.at && b0.min != null ? money(b0.min) : ""}</td>
      <td class="num">${med}</td>
      <td><div class="tb-chips">${chips}</div></td>
      <td class="num tb-dim">${b0.at ? ago(now() - b0.at) + " 전" : ""}</td>
      <td class="tb-acts">${link}${rxBtn}</td>
    </tr>`;
  }

  function render() {
    const q = S.q.trim();
    let list = J.filter(({ m }) => (!S.base || m.base === S.base)
      && (S.affix === "all" || m.affix === S.affix) && (!q || m.text.includes(q)));
    if (S.only) list = list.filter((r) => (r.bands[0].med ?? -1) >= S.th);
    list.sort((a, b) => (b.bands[0].med ?? -1) - (a.bands[0].med ?? -1));
    $("[data-hbase]").hidden = !!S.base;
    for (const u of el.querySelectorAll("[data-unit]")) u.textContent = unitName();
    $("[data-count]").textContent = `${list.length}개 옵션`;
    $("[data-rows]").innerHTML = list.map(row).join("")
      || `<tr><td colspan="10" class="tb-empty">조건에 맞는 옵션이 없습니다.</td></tr>`;
    combos(list);
  }

  /** 통합 정규식 — 지금 보이는 옵션 전부를 하나로 묶는다.

      표에 걸린 필터(서판 종류·기준·접두/접미·검색어)를 그대로 따른다. 창고를 한 번에
      훑는 쪽이라 서판 종류는 박지 않는다 — 한 창고에 여러 종류가 섞여 있다.

      검색창이 250자까지라 넘치면 조각으로 자른다. 나눠 붙여 넣으면 된다. */
  function combos(list) {
    const box = $("[data-combo]");
    if (!box) return;
    // 같은 문구가 여러 서판에 걸쳐 있다. 종류를 안 박으므로 한 번만 넣는다.
    const seen = new Set();
    const terms = [];
    for (const r of list) {
      const t = hitRx(r);
      if (!t || seen.has(t)) continue;
      seen.add(t);
      terms.push(t);
    }
    const parts = chunk(terms);
    box.hidden = !parts.length;
    if (!parts.length) return;
    const one = parts.length === 1;
    box.innerHTML = `<span class="tb-combo-lab" title="지금 표에 보이는 옵션 ${terms.length}개를 하나로 묶습니다. `
      + `수치는 걸지 않습니다 — 그 옵션이 붙었는지만 봅니다">통합 정규식</span>`
      + parts.map((p, i) => `<button type="button" class="tb-rx" data-rx="${esc(p)}"
          title="${esc(`${p.length}자 — ${p}`)}">${one ? "복사" : i + 1} <b>${p.length}자</b></button>`).join("")
      + (one ? "" : `<span class="tb-dim">${parts.length}조각으로 나눠 붙여 넣으세요</span>`);
  }

  function set(key, v) { S[key] = v; savePrefs(S); controls(); render(); }

  /** 클립보드. https 가 아니거나 권한이 막히면 writeText 가 없거나 던진다 — 그때는 숨은
      textarea 로 물러선다(경로석 화면과 같다). */
  async function copy(text) {
    try { await navigator.clipboard.writeText(text); return true; } catch { /* 아래로 */ }
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.cssText = "position:fixed;top:-1000px;opacity:0";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      ta.remove();
      return ok;
    } catch { return false; }
  }

  // 앞서 누른 버튼이 아직 '복사됨' 이면 그것부터 되돌린다 — 안 그러면 잇달아 누를 때
  // 앞 버튼이 그대로 남고, 같은 버튼을 두 번 누르면 원래 글자를 잃는다.
  let pending = null, undo = 0;
  function restore() {
    clearTimeout(undo);
    if (!pending) return;
    pending.el.innerHTML = pending.was;
    pending.el.classList.remove("hit");
    pending = null;
  }
  async function copied(b) {
    restore();
    pending = { el: b, was: b.innerHTML };
    b.textContent = (await copy(b.dataset.rx)) ? "복사됨" : "실패";
    b.classList.add("hit");
    undo = setTimeout(restore, 1200);
  }

  el.addEventListener("click", (e) => {
    const rx = e.target.closest("button.tb-rx");
    if (rx) return void copied(rx);
    const b = e.target.closest("[data-seg] button");
    if (b) set(b.parentElement.dataset.seg, b.dataset.v);
  });
  $("[data-th]").addEventListener("input", (e) => { S.th = Number(e.target.value) || 0; savePrefs(S); render(); });
  $("[data-only]").addEventListener("change", (e) => set("only", e.target.checked));
  $("[data-q]").addEventListener("input", (e) => { S.q = e.target.value; savePrefs(S); render(); });

  (async () => {
    try {
      C = await grab(el.dataset.catalog);
    } catch (e) {
      $("[data-veil-note]").textContent = `옵션 목록을 불러오지 못했습니다 — ${e.message}`;
      return;
    }
    await loadPrices();
    $("[data-veil]").remove();
    $("[data-app]").hidden = false;
    controls();
    status();
    render();
    setInterval(async () => { await loadPrices(); status(); render(); }, REFRESH_MS);
    setInterval(status, 60 * 1000);      // '몇 분 전' 과 경고는 값이 안 바뀌어도 흐른다
  })();
}
