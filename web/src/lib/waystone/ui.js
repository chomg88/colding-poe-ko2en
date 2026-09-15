/* 경로석 시세 화면.

   서판과 달리 빌드에 들어가는 카탈로그가 없다. 무엇을 물어봤는지(축·구간)를 수집기가
   시세 파일에 같이 실어 보내므로, 이 화면은 파일 하나만 받아 표를 그린다.

   값은 사이트 배포와 따로 움직이고 운영자 PC 가 꺼지면 멈춘다 — 마지막 갱신 시각을 늘
   보여 주고, 오래되면 표 위에 경고를 띄운다(서판 화면과 같다). */

const TRADE = "https://poe.kakaogames.com/trade2/search/poe2";
const REFRESH_MS = 5 * 60 * 1000;
const STORE = "colding-waystone";
// 호가가 1~2카오스에 몰려 있어 엑잘로 보면 40/80 두 값만 오간다 — 카오스가 기본이다.
const DEF = { cur: "ch" };

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
  let S = { ...DEF };
  try { S = { ...DEF, ...JSON.parse(localStorage.getItem(STORE) || "{}") }; } catch { /* 없어도 돈다 */ }
  let P = null;
  let perr = "";

  /* 고른 화폐의 환율이 파일에 없으면 엑잘로 보인다 — 수집기는 어긋난 환율을 빼고 올린다.
     단위 이름도 같이 따라가야 엑잘 값에 '카오스' 가 붙지 않는다(서판 화면의 inDiv 와 같다). */
  const cur = () => (S.cur === "div" && P?.rates?.divine ? "div" : S.cur === "ch" && P?.rates?.chaos ? "ch" : "ex");
  const rate = () => ({ div: P?.rates?.divine, ch: P?.rates?.chaos })[cur()] || 1;
  const unitName = () => ({ div: "디바인", ch: "카오스" })[cur()] || "엑잘";
  function money(ex) {
    if (ex == null) return "-";
    const v = ex / rate();
    return v >= 100 ? Math.round(v).toLocaleString() : v >= 10 ? v.toFixed(0) : v >= 1 ? v.toFixed(1) : v.toFixed(2);
  }

  const rec = (tier, axis, band) => P?.b?.[axis ? `${tier}:${axis}:${band}` : `${tier}:base`] || null;

  /** 표의 한 줄 = 축의 한 구간. 등급마다 칸을 따로 둔다 — 같은 구간이라도 15·16등급 값이
      몇 배씩 차이 난다. 그 등급에서 안 보는 구간은 흐린 '-' 다(기다려도 값이 오지 않는다). */
  function cell(tier, axis, band, bands) {
    if (axis && !bands.includes(band)) {
      return `<td class="num ws-off" title="${tier}등급에는 이 구간이 없습니다 — 그만큼 높게 굴러가지 않습니다">-</td>
              <td class="num ws-off">-</td>`;
    }
    const r = rec(tier, axis, band);
    if (!r) return `<td class="num ws-dim">대기</td><td class="num ws-dim"></td>`;
    if (r[6]) return `<td class="num ws-err" title="${esc(r[6])}">오류</td><td class="num ws-dim"></td>`;
    const val = r[4] != null ? money(r[4]) : "매물 없음";
    const tip = `최저 ${money(r[3])} ${unitName()} · 값 낸 매물 ${r[2]} · ${ago(now() - r[0])} 전`;
    const inner = r[5]
      ? `<a href="${TRADE}/${encodeURIComponent(P.league)}/${esc(r[5])}" target="_blank" rel="noopener" title="${esc(tip)}">${val}</a>`
      : `<span title="${esc(tip)}">${val}</span>`;
    return `<td class="num ws-val">${inner}</td>
            <td class="num ws-dim" title="즉시구입 매물 수. 10,000 은 거래소가 세다 만 것입니다">${r[1].toLocaleString()}</td>`;
  }

  function rows() {
    const out = [`<tr class="ws-floor">
      <td class="ws-axis">등급 바닥</td><td class="num ws-dim">조건 없음</td>
      ${P.tiers.map((t) => cell(t, null, null, [])).join("")}</tr>`];
    for (const a of P.axes) {
      // 등급마다 상한이 달라 구간이 다르다 — 둘을 합쳐 한 줄씩 그린다
      const all = [...new Set(P.tiers.flatMap((t) => a.bands[String(t)] || []))].sort((x, y) => x - y);
      out.push(...all.map((band, i) => `<tr${i === 0 ? ' class="ws-first"' : ""}>
        <td class="ws-axis">${i === 0 ? esc(a.label) : ""}</td>
        <td class="num">${band}${esc(a.unit)}+</td>
        ${P.tiers.map((t) => cell(t, a.id, band, a.bands[String(t)] || [])).join("")}</tr>`));
    }
    return out.join("");
  }

  function status() {
    const alert = $("[data-alert]");
    let level = "", msg = "";
    if (!P) {
      level = "bad";
      msg = `시세 파일을 받지 못했습니다(${perr}). 잠시 뒤 다시 열어 주세요.`;
    } else {
      const h = (now() - P.updatedAt) / 3600;
      if (!P.updatedAt) {
        level = "warn";
        msg = "아직 모으는 중입니다. 한 바퀴 도는 데 30분쯤 걸립니다.";
      } else if (h >= badH) {
        level = "bad";
        msg = `수집이 ${ago(now() - P.updatedAt)} 전에 멈췄습니다. 사고팔기 전에 거래소 링크로 직접 확인하세요.`;
      } else if (h >= warnH) {
        level = "warn";
        msg = `마지막 갱신이 ${ago(now() - P.updatedAt)} 전입니다 — 값이 조금 늦을 수 있습니다.`;
      }
    }
    alert.hidden = !level;
    alert.className = `tb-alert ${level}`;
    alert.textContent = msg;

    const box = $("[data-status]");
    if (!P) { box.innerHTML = `<span>시세 없음</span>`; return; }
    const p = P.progress || [0, 0];
    box.innerHTML = [
      `<span>${esc(P.league)}</span>`,
      `<span>마지막 갱신 <b>${P.updatedAt ? ago(now() - P.updatedAt) + " 전" : "-"}</b></span>`,
      `<span title="축·구간마다 하나씩 물어봅니다">구간 <b>${p[0]}/${p[1]}</b></span>`,
      P.rates?.chaos ? `<span>1 카오스 = <b>${Math.round(P.rates.chaos)}</b> 엑잘</span>` : "",
      P.rates?.divine ? `<span>1 디바인 = <b>${Math.round(P.rates.divine)}</b> 엑잘</span>` : "",
      perr ? `<span class="tb-err">새 값을 못 받음 — ${esc(perr)}</span>` : "",
    ].join("");
  }

  function render() {
    if (!P) return;
    $("[data-head]").innerHTML = `<tr><th>속성</th><th class="num">구간</th>`
      + P.tiers.map((t) => `<th class="num">${t}등급 <span class="tb-unit">${unitName()}</span></th>`
        + `<th class="num">매물</th>`).join("") + `</tr>`;
    $("[data-rows]").innerHTML = rows();
    for (const b of el.querySelectorAll('[data-seg="cur"] button'))
      b.setAttribute("aria-pressed", String(b.dataset.v === S.cur));
  }

  async function load() {
    try {
      // raw.githubusercontent 는 5분쯤 캐시한다. 분 단위로 주소를 바꿔 그보다 안 묵게.
      P = await grab(`${el.dataset.prices}?v=${Math.floor(Date.now() / 60000)}`, { cache: "no-store" });
      perr = "";
    } catch (e) {
      perr = e.message;       // 전에 받은 값이 있으면 그대로 두고 경고만 띄운다
    }
  }

  el.addEventListener("click", (e) => {
    const b = e.target.closest('[data-seg="cur"] button');
    if (!b) return;
    S.cur = b.dataset.v;
    try { localStorage.setItem(STORE, JSON.stringify(S)); } catch { /* 저장 못 해도 돈다 */ }
    render();
  });

  (async () => {
    await load();
    if (!P) {
      $("[data-veil-note]").textContent = `시세를 불러오지 못했습니다 — ${perr}`;
      return;
    }
    $("[data-veil]").remove();
    $("[data-app]").hidden = false;
    status();
    render();
    setInterval(async () => { await load(); status(); render(); }, REFRESH_MS);
    setInterval(status, 60 * 1000);      // '몇 분 전' 은 값이 안 바뀌어도 흐른다
  })();
}
