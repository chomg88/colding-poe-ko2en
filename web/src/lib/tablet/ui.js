/* 서판 시세 화면.

   카탈로그(무엇을 물어봤나)는 빌드에 박힌 해시 파일이고, 값은 운영자 PC 의 수집기가
   GitHub data 브랜치에 올리는 tablet-prices.json 이다. 둘을 구간 키로 잇는다.

   값은 사이트 배포와 따로 움직이고, 운영자 PC 가 꺼지면 멈춘다. 그래서 마지막 갱신
   시각을 늘 보여 주고, 오래되면 표 위에 경고를 띄운다(data-warn / data-bad 시간). */

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

/** 수치 칩 라벨의 단위 — 옵션 문구에서 # 바로 뒤. "#% 증가" → "%", "#초" → "초" */
function unitOf(text) {
  const m = /#\s*(%|초|개|회|마리|명)/.exec(text);
  return m ? m[1] : "";
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
      <td>${link}</td>
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
  }

  function set(key, v) { S[key] = v; savePrefs(S); controls(); render(); }

  el.addEventListener("click", (e) => {
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
