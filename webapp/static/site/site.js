// Сайт-презентация (/about): возможности-аккордеон, демо в телефоне и живой
// поиск расписания МИРЭА (/about/api/search, /about/api/target).
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  const arrow = (d) => '<svg><use href="#' + (d ? "arrow-d" : "arrow") + '"/></svg>';
  const spinner = (t) => '<p class="state-text"><span class="spinner"></span> ' + t + '</p>';

  // демо: заглушка «Открываем приложение…», пока приложение не нарисовало
  // первый кадр (site/demo-app.js шлёт «uib-demo-ready»); страница iframe
  // грузится раньше, чем Flutter запустится, — поэтому не по load, а по
  // сигналу, и на всякий случай через 15 с после load
  const frame = $("demo-frame");
  if (frame) {
    const ready = () => $("demo-loading").classList.add("loaded");
    window.addEventListener("message", (e) => {
      if (e.origin === location.origin && e.data === "uib-demo-ready") ready();
    });
    frame.addEventListener("load", () => setTimeout(ready, 15000));
  }

  // «Поделиться» — системное меню телефона (там же Telegram); где его нет —
  // кнопка скрыта, ссылку и так видно в адресной строке
  const share = $("share-site");
  if (share && navigator.share) {
    share.hidden = false;
    share.addEventListener("click", () => navigator.share({
      title: "Капибара", text: "Учёба МИРЭА: расписание, дедлайны и баллы СДО, лекции и ИИ по ним",
      url: location.origin + "/about",
    }).catch(() => {}));
  }

  // ── возможности ──
  const FEATURES = [
    { label: "Сегодня", title: "День, собранный за тебя",
      text: "Пары, аудитории, погода и ближайшие дедлайны — на одном экране. Видно, что идёт сейчас и куда идти дальше. Утром бот присылает сводку в личку.",
      note: "Открой «Сегодня» в демо и полистай дни недели." },
    { label: "СДО", title: "Баллы без лишних вкладок",
      text: "Баллы по предметам, посещения и сколько осталось до зачёта или нужной оценки, правило 75 %. Задание можно открыть и сдать работу прямо из Telegram.",
      note: "В демо можно посмотреть предметы и цель по предмету." },
    { label: "Файлы", title: "Лекции, которые находятся",
      text: "Материалы курсов разложены по предметам и типам, конспект — одной кнопкой. А поиск ищет и внутри лекций: «дисконтирование» — и видно лекцию, слайд и отрывок.",
      note: "Открой «Ещё → Файлы» в приложении." },
    { label: "ИИ", title: "Ответы с опорой на лекции",
      text: "Задай вопрос своими словами. ИИ ищет по смыслу в лекциях группы и показывает слайд, из которого взял ответ.",
      note: "В разделе «Чат» демо показывает пример ответа." },
  ];
  let feature = 0;
  const list = $("features");
  function renderFeatures() {
    list.innerHTML = FEATURES.map((f, i) => {
      const open = feature === i;
      return '<article class="feature-row' + (open ? " open" : "") + '"><h3><button class="feature-toggle" data-i="' + i +
        '" aria-expanded="' + open + '" aria-controls="feature-' + i + '"><span class="feature-number">0' + (i + 1) +
        '</span><span><small>' + f.label + '</small><span class="feature-title">' + f.title + '</span></span>' +
        '<span class="toggle-sign" aria-hidden="true">' + (open ? "−" : "+") + '</span></button></h3>' +
        '<div id="feature-' + i + '" class="feature-detail"' + (open ? "" : " hidden") + '><p>' + f.text +
        '</p><p class="feature-note"><span>↳</span>' + f.note + '</p></div></article>';
    }).join("");
  }
  list.addEventListener("click", (e) => {
    const b = e.target.closest(".feature-toggle");
    if (!b) return;
    feature = feature === +b.dataset.i ? -1 : +b.dataset.i;
    renderFeatures();
  });
  document.querySelectorAll("[data-feature]").forEach((a) =>
    a.addEventListener("click", () => { feature = +a.dataset.feature; renderFeatures(); }));
  renderFeatures();

  // ── поиск расписания ──
  const KINDS = { 1: "Группа", 2: "Преподаватель", 3: "Аудитория" };
  const q = $("schedule-query"), out = $("finder-out"), sched = $("finder-schedule");
  const go = document.querySelector(".search-submit");
  let timer = null, seq = 0, items = [], selected = null, data = null, week = 0;

  async function getJSON(url) {
    const r = await fetch(url);
    if (r.status === 429) throw new Error("Слишком много запросов. Подожди минуту и попробуй ещё раз.");
    if (!r.ok) throw new Error("Расписание сейчас недоступно. Попробуй ещё раз чуть позже.");
    return r.json();
  }

  function idle() {
    out.innerHTML = '<div class="finder-empty"><span class="empty-calendar" aria-hidden="true"><svg viewBox="0 0 60 60" fill="none">' +
      '<rect x="9" y="13" width="42" height="39" rx="3"/><path d="M9 24h42M20 7v12M40 7v12M19 34h6m10 0h6m-22 9h6m10 0h6"/></svg></span>' +
      '<p>Чьё расписание посмотрим?</p><span>Начни вводить название группы, фамилию<br class="desktop-break"> преподавателя или номер аудитории.</span></div>';
  }

  function changed() {
    seq++; selected = null; data = null; sched.innerHTML = "";
    go.disabled = q.value.trim().length < 2;
    clearTimeout(timer);
    if (q.value.trim().length < 2) { idle(); return; }
    out.innerHTML = spinner("Ищем в расписании МИРЭА…");
    timer = setTimeout(search, 300);
  }

  async function search() {
    const my = ++seq, text = q.value.trim();
    if (text.length < 2) { idle(); return; }
    out.innerHTML = spinner("Ищем в расписании МИРЭА…");
    try {
      const res = await getJSON("/about/api/search?q=" + encodeURIComponent(text));
      if (my !== seq) return;
      items = (res.items || []).slice(0, 10);
      renderResults();
    } catch (e) {
      if (my === seq) out.innerHTML = '<div class="error-message"><p>' + esc(e.message) +
        '</p><button class="text-link" data-retry="search">Повторить поиск ↗</button></div>';
    }
  }

  function renderResults() {
    out.innerHTML = items.length
      ? '<div class="search-results" aria-label="Результаты поиска">' + items.map((it, i) => {
          const on = selected && selected.id === it.id && selected.type === it.type;
          return '<button data-i="' + i + '" class="' + (on ? "selected" : "") + '" aria-pressed="' + !!on + '"><span>' +
            esc(it.title) + '<small>' + esc(it.hint || KINDS[it.type] || "") + '</small></span>' + arrow(true) + '</button>';
        }).join("") + '</div>'
      : '<p class="state-text">Ничего не найдено. Попробуй другую фамилию или часть названия группы.</p>';
  }

  async function open(it) {
    const my = ++seq;
    selected = it; data = null;
    renderResults();
    sched.innerHTML = spinner("Загружаем расписание…");
    try {
      const res = await getJSON("/about/api/target/" + it.type + "/" + it.id);
      if (my !== seq) return;
      if (!Array.isArray(res.weeks)) throw new Error("Не удалось прочитать расписание.");
      data = res; week = 0;
      renderSchedule();
    } catch (e) {
      if (my === seq) sched.innerHTML = '<div class="error-message"><p>' + esc(e.message) +
        '</p><button class="text-link" data-retry="open">Попробовать ещё раз ↗</button></div>';
    }
  }

  function day(iso, opts) {
    return new Date(iso + "T12:00:00").toLocaleDateString("ru-RU", opts);
  }

  function renderSchedule() {
    const s = data;
    let body;
    if (!s.weeks.length) body = '<p class="state-text">Расписание пока не опубликовано.</p>';
    else {
      const tabs = s.weeks.map((w, i) => '<button data-w="' + i + '" class="' + (week === i ? "active" : "") + '" aria-pressed="' + (week === i) + '">' +
        (i === 0 ? "Эта неделя" : i === 1 ? "Следующая неделя" : "Неделя " + (w.week || i + 1)) +
        (w.week ? '<span> / ' + w.week + '</span>' : "") + '</button>').join("");
      const days = s.weeks[week].days.filter((d, i) => i < 6 || d.lessons.length).map((d) => {
        const today = d.date === s.today;
        const lessons = d.lessons.length ? d.lessons.map((l) =>
          '<div class="lesson' + (l.status === "now" ? " now" : "") + '"><time>' + esc(l.start) + '<span>' + esc(l.end) + '</span></time>' +
          '<div><b>' + esc(l.title) + '</b><p>' + esc([l.kind, l.room, s.type === 2 ? l.groups : l.teacher].filter(Boolean).join(" · ")) +
          '</p></div></div>').join("") : '<span class="free-day">Без пар</span>';
        return '<div class="schedule-day' + (today ? " today" : "") + '"><div class="day-label"><b>' + day(d.date, { weekday: "long" }) +
          '</b><span>' + day(d.date, { day: "numeric", month: "long" }) + (today ? " · сегодня" : "") + '</span></div><div>' + lessons + '</div></div>';
      }).join("");
      body = '<div class="week-switch" aria-label="Неделя расписания">' + tabs + '</div><div>' + days + '</div>';
    }
    // подписка на тот же календарь МИРЭА: телефон сам подтягивает изменения
    const ical = "english.mirea.ru/schedule/api/ical/" + (+s.type) + "/" + (+s.id);
    body += '<div class="cal-row"><a class="cal-sub" href="webcal://' + ical + '">+ В календарь телефона</a>' +
      '<button type="button" class="cal-copy" data-ical="https://' + ical + '">скопировать ссылку</button>' +
      '<span>обновляется само · на Android — ссылку в Google Календарь</span></div>';
    sched.innerHTML = '<div class="schedule-result"><div class="schedule-heading"><div><p class="eyebrow">' + (KINDS[s.type] || "Расписание") +
      '</p><h3>' + esc(s.title) + '</h3></div><span class="live-label"><i></i> ' + (s.stale ? "Сохранённая копия" : "Актуальное расписание") +
      '</span></div>' + body + '</div>';
  }

  q.addEventListener("input", changed);
  $("finder-form").addEventListener("submit", (e) => { e.preventDefault(); clearTimeout(timer); search(); });
  document.querySelectorAll(".search-examples button").forEach((b) =>
    b.addEventListener("click", () => { q.value = b.textContent; changed(); }));
  out.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.retry) search();
    else if (b.dataset.i !== undefined) open(items[+b.dataset.i]);
  });
  sched.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    if (b.dataset.ical) {
      const done = () => { b.textContent = "скопировано"; setTimeout(() => (b.textContent = "скопировать ссылку"), 1600); };
      if (navigator.clipboard) navigator.clipboard.writeText(b.dataset.ical).then(done, () => prompt("Ссылка на календарь", b.dataset.ical));
      else prompt("Ссылка на календарь", b.dataset.ical);
      return;
    }
    if (b.dataset.retry && selected) open(selected);
    else if (b.dataset.w !== undefined) { week = +b.dataset.w; renderSchedule(); }
  });
  idle();
})();
