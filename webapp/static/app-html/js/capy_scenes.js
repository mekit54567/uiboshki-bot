// Капибара, пока грузится (app/lib/widgets/capy_refresh.dart): при первой
// загрузке экрана — сцена с подписью (capyLoading, вместо крутилки);
// потянул экран вниз — маленькая сцена сверху (pullRefresh). Сцены идут по
// кругу: сёрф, ноутбук, лампа, мяч, мандарин; ночью — спит. Движение — CSS.
"use strict";

const CAPY_SCENE_TEXT = { surf: "ловлю волну…", laptop: "печатаю…", lamp: "листаю…", ball: "обновляю…", mandarin: "держу мандарин…", sleep: "сплю, но обновляю…" };
const CAPY_DAY = ["surf", "laptop", "lamp", "ball", "mandarin"];
let _capyNext = Math.floor(Math.random() * CAPY_DAY.length);
/** Следующая сцена: ночью — сон, днём — по кругу (CapyScenes.next). */
function nextCapyScene(hour = msk(now()).h) {
  if (hour >= 23 || hour < 5) return "sleep";
  return CAPY_DAY[_capyNext++ % CAPY_DAY.length];
}
const WAVE_CHANCE = 30; // «идеальная волна» — полночная ачивка, раз в 30 сёрфов

/** Волна SVG: синусоида длиной len, высотой h от низа, бежит влево на len за круг. */
function capyWave(w, H, height, len, amp, alpha, dur) {
  const base = H - height + amp;
  let d = `M0 ${H}`;
  for (let x = 0; x <= w + len + 2; x += 3) d += ` L${x} ${(base + amp * Math.sin((x / len) * 2 * Math.PI)).toFixed(1)}`;
  d += ` L${w + len + 2} ${H} Z`;
  return `<svg class="cs-wave" width="${w + len + 2}" height="${H}" style="animation-duration:${dur}ms;--len:${len}px">
    <path d="${d}" fill="#4F8CFF" fill-opacity="${alpha}"/></svg>`;
}
/** Сама сцена w×h (CapySceneView). */
function capyScene(scene, w = 220, h = 110) {
  const pic = (pose, size, left, top, cls = "") => `<i class="capy ${cls}" style="--img:url(/img/capy/${pose}.png);width:${size}px;height:${size}px;position:absolute;left:${left}px;top:${top}px"></i>`;
  let inner = "";
  if (scene === "surf") {
    const size = 112, top = h - 18 - size * 0.81;
    inner = capyWave(w, h, 30, 96, 5, 0.3, 2600)
      + [0, 1, 2].map((k) => `<i class="cs-spray" style="left:${w / 2 - 34 - k * 5}px;top:${h - 22 + k * 2}px;animation-delay:${-k * 867}ms"></i>`).join("")
      + `<div class="cs-surf" style="left:${w / 2 - size / 2}px;top:${top}px">${pic("surf", size, 0, 0)}</div>`
      + capyWave(w, h, 18, 70, 4, 0.5, 1300);
  } else if (scene === "laptop" || scene === "mandarin") {
    const size = 76, left = w / 2 - size / 2, top = h - size - 4;
    inner = pic("day", size, left, top);
    if (scene === "laptop") inner += [0, 1, 2].map((k) => `<i class="cs-dot" style="left:${left + size * 0.66 + k * 8}px;top:${top + size * 0.3}px;animation-delay:${k * 154}ms"></i>`).join("");
    else inner += `<i class="cs-mandarin" style="left:${left + size * 0.5 - 8}px;top:${top + size * 0.11 - 15}px"><b></b><s></s></i>`;
  } else if (scene === "lamp") {
    const size = 76, left = w / 2 - size / 2, top = h - size - 4;
    inner = `<i class="cs-glow" style="left:${left + size * 0.76 - 40}px;top:${top + size * 0.36 - 40}px"></i>` + pic("evening", size, left, top);
  } else if (scene === "ball") {
    const size = 74;
    inner = `<i class="cs-shadow" style="left:${w / 2 - 22}px"></i>` + pic("joy", size, w / 2 - size / 2, h - size - 6, "cs-bounce");
  } else {
    const size = 74, left = w / 2 - size / 2, top = h - size - 2;
    inner = pic("night", size, left, top)
      + [0, 1].map((k) => `<b class="cs-z" style="left:${left + size * 0.74}px;top:${top + size * 0.1}px;font-size:${10 + k * 3}px;animation-delay:${-k * 1200}ms">z</b>`).join("");
  }
  return `<div class="cs" data-scene="${scene}" style="width:${w}px;height:${h}px">${inner}</div>`;
}
/** Вместо крутилки при первой загрузке: сцена и подпись (CapyLoading). */
function capyLoading() {
  const scene = nextCapyScene(), wave = scene === "surf" && Math.floor(Math.random() * WAVE_CHANCE) === 0;
  if (wave) Ach.unlock("wave");
  return `<div class="cs-loading" role="status" aria-label="Загружаю">${capyScene(scene)}
    <div class="bd mut" style="--sz:13px;margin-top:6px">${wave ? "идеальная волна!" : CAPY_SCENE_TEXT[scene]}</div></div>`;
}

/** «Потяни, чтобы обновить» с капибарой (CapyRefresh): onRefresh → Promise. */
function pullRefresh(screen, onRefresh) {
  const sc = screen.scroller, CARD = 56;
  const card = document.createElement("div");
  card.className = "cs-pull";
  screen.appendChild(card);
  const gap = (on) => { const c = sc.firstElementChild; if (c) { c.style.transition = "transform .26s cubic-bezier(.2,.8,.2,1)"; c.style.transform = on ? "translateY(64px)" : ""; } };
  let y0 = null, drag = 0, busy = false, armed = false, scene = "surf";
  const place = (v) => {
    card.style.opacity = Math.min(1, v);
    card.style.transform = `translateY(${-(CARD + 8) * (1 - Math.min(1, v))}px)`;
  };
  sc.addEventListener("touchstart", (e) => {
    if (busy || sc.scrollTop > 0 || Sheet.open.length) { y0 = null; return; }
    y0 = e.touches[0].clientY; drag = 0; armed = false;
  }, { passive: true });
  sc.addEventListener("touchmove", (e) => {
    if (y0 === null || busy) return;
    const dy = e.touches[0].clientY - y0;
    if (dy <= 0 || sc.scrollTop > 0) { if (drag) place(0); drag = 0; return; }
    if (!drag) { // новый жест — новая сцена
      card.style.top = sc.getBoundingClientRect().top - screen.getBoundingClientRect().top + parseFloat(getComputedStyle(sc).paddingTop) + "px";
      scene = nextCapyScene();
      card.innerHTML = `<div style="width:132px;height:${CARD}px;overflow:hidden"><div style="transform:scale(.6);transform-origin:0 0">${capyScene(scene, 220, 94)}</div></div>`;
      card.classList.add("on");
    }
    drag = dy * 0.5; // сопротивление, как у RefreshIndicator
    const full = sc.clientHeight / 6;
    if (!armed && drag >= full) { armed = true; tick(); }
    if (armed && drag < full) armed = false;
    card.style.transition = "none";
    place(drag / full);
  }, { passive: true });
  sc.addEventListener("touchend", async () => {
    if (y0 === null || busy) return;
    y0 = null;
    card.style.transition = "";
    if (!armed) { place(0); return; }
    busy = true;
    place(1);
    gap(true);
    if (scene === "surf" && Math.floor(Math.random() * WAVE_CHANCE) === 0) Ach.unlock("wave");
    try { await onRefresh(); } catch (e) {} finally {
      busy = false;
      gap(false);
      place(0);
    }
  });
}
