// «Сдать» (app/lib/screens/deadlines.dart, deadline_edit.dart, submit.dart,
// task.dart, widgets/report.dart, widgets/cheer.dart): переключатель
// «Впереди · N | Сдано · N»; во «Впереди» — горящее (меньше суток) большой
// карточкой с обратным отсчётом и кнопкой «Сдать», ниже — по неделям с датой
// слева (сегодня — красным, завтра — жёлтым), в конце — «Срок прошёл».
// Свайп вправо — «сдал» (у сданного — «вернуть»), нажатие — действия, «+» —
// свой срок. Сверху — входы в «ДЗ группы» и «Заметки» (homework.js).
// Снаружи: openTask(work, course) — экран задания СДО, dlSubmitSheet —
// «Сдать файлом», openReportMenu(kind, id, reload) — «⋯» у чужой записи,
// cheer() — порадоваться отметке «сдано».
"use strict";

// ── Модель срока (Deadline + DlExtra) ──
function dlOf(j) {
  const reminders = (Array.isArray(j.reminders) ? j.reminders : []).map((r) => ({ at: String(r.at), label: String(r.label) }));
  const d = {
    raw: j, id: j.id, subject: j.subject || "", dueDate: j.due_date || "", dueTime: j.due_time || "",
    done: j.done === 1 || j.done === true, canSubmit: j.can_submit === true,
  };
  d.due = dueOf({ due_date: d.dueDate, due_time: d.dueTime });
  if (isNaN(d.due)) d.due = new Date("2100-01-01T00:00:00+03:00");
  d.x = {
    description: String(j.description || "").trim(), personal: j.personal === true, mineChanged: j.mine_changed === true,
    canEdit: j.can_edit === true, reportable: j.reportable === true, editScope: j.edit_scope || "me", reminders,
    timeLimit: typeof j.time_limit === "number" ? Math.trunc(j.time_limit) : null,
  };
  d.x.isLink = /^https?:\/\//.test(d.x.description);
  return d;
}
/** Время теста из СДО: «15 мин», «1 ч», «1 ч 30 мин»; без ограничения — null. */
function dlQuizTime(min) {
  if (min == null || min <= 0) return null;
  const h = Math.floor(min / 60), m = min % 60;
  if (!h) return `${m} мин`;
  return m ? `${h} ч ${m} мин` : `${h} ч`;
}
/** Пометки есть — с time считается и время теста (только в новом дизайне). */
function dlHasChips(x, time = false) {
  return !!x && (x.personal || x.mineChanged || x.reminders.length > 0 || (time && dlQuizTime(x.timeLimit) != null));
}
/** «Практика 5-6 · Анализ данных (Экз)» → работа и предмет (splitTitle). */
function dlSplit(subject) {
  const i = subject.lastIndexOf(" · ");
  if (i <= 0) return { task: subject.trim(), course: "" };
  return { task: subject.slice(0, i).trim(), course: subject.slice(i + 3).replace(/\s*\((Экз|Зач)\)\s*$/, "").trim() };
}
/** Номер дня по Москве — для «сколько дней между» по календарю. */
function dlDayNo(date) { const t = msk(date); return Date.UTC(t.y, t.m - 1, t.d) / 864e5; }
function dlDays(at, d) { return dlDayNo(d) - dlDayNo(at); }
function dlTime(d) { return d.dueTime || "23:59"; }
function dlDueLabel(d) {
  const t = msk(d.due);
  return `${WD_SHORT[t.wd].toLowerCase()}, ${t.d} ${MONTHS[t.m - 1]} · ${dlTime(d)}`;
}
/** Подпись недели: «Эта неделя», «Следующая», дальше — даты недели. */
function dlWeekLabel(monday, at) {
  const n = Math.floor((dlDayNo(new Date(monday + "T12:00:00+03:00")) - dlDayNo(new Date(mondayOf(at) + "T12:00:00+03:00"))) / 7);
  if (n <= 0) return "Эта неделя";
  if (n === 1) return "Следующая";
  const a = msk(new Date(monday + "T12:00:00+03:00")), b = msk(new Date(addDays(monday, 6) + "T12:00:00+03:00"));
  return a.m === b.m ? `${a.d}–${b.d} ${MONTHS[b.m - 1]}` : `${a.d} ${MONTHS[a.m - 1]} – ${b.d} ${MONTHS[b.m - 1]}`;
}
/** Последняя проверка СДО группы: null — не проверяли. */
function dlSdo(j) {
  if (!j || typeof j !== "object" || typeof j.ok !== "boolean") return null;
  const at = (v) => { if (typeof v !== "string") return null; const t = new Date(v); return isNaN(t) ? null : t; };
  return { ok: j.ok, checkedAt: at(j.checked_at), lastOk: at(j.last_ok) };
}
/** «СДО проверено в 12:40» / «вчера в 12:40» / «10 октября в 12:40». */
function dlSdoChecked(checked, at) {
  const n = dlDays(checked, at), t = msk(checked);
  const day = n <= 0 ? "" : n === 1 ? "вчера " : `${t.d} ${MONTHS[t.m - 1]} `;
  return `СДО проверено ${day}в ${hm(checked)}`;
}
/** «Показываю сроки от 09:41» / «от вчера, 09:41» / «от 10 октября, 09:41». */
function dlSdoShown(lastOk, at) {
  if (!lastOk) return "Новые сроки пока не подтянулись";
  const n = dlDays(lastOk, at), t = msk(lastOk);
  const day = n <= 0 ? "" : n === 1 ? "вчера, " : `${t.d} ${MONTHS[t.m - 1]}, `;
  return `Показываю сроки от ${day}${hm(lastOk)}`;
}
/** Число без лишних нулей: 7 → «7», 7.5 → «7,5» (fmtNum). */
function dlNum(v) { v = Number(v) || 0; return v === Math.round(v) ? String(Math.round(v)) : v.toFixed(1).replace(".", ","); }

/** Пометки срока (DlChips): время теста, личный, изменён у тебя, напоминания. */
function dlChips(x, time = true) {
  const chip = (ic, text, c) => `<span class="dl-tag" style="--c:${c}">${icon(ic, ic === "person_outline" || ic === "edit" || ic === "timer" ? "o" : "")}${esc(text)}</span>`;
  let out = "";
  if (time && Theme.design2 && dlQuizTime(x.timeLimit)) out += chip("timer", dlQuizTime(x.timeLimit), "var(--muted)");
  if (x.personal) out += chip("person_outline", "личный", "var(--muted)");
  if (x.mineChanged) out += chip("edit", "изменён у тебя", "var(--accent)");
  for (const r of x.reminders) out += chip("notifications_none", r.label, "var(--warn)");
  return `<div class="dl-tags">${out}</div>`;
}
/** Строка «● Анализ данных · 18:00»: точка цвета предмета, предмет и время. */
function dlSubjectLine(course, rest, size = 13) {
  const text = [course, rest].filter(Boolean).join(" · ");
  return `<div class="bd mut" style="--sz:${size}px">${course ? `<i class="cm-dot dl-dot" style="background:${ink(course)}"></i>` : ""}${esc(text)}</div>`;
}

// ── Порадоваться «сдано» (widgets/cheer.dart): капибара или конфетти ──
function dlCheer() {
  const kind = (Theme.design2 ? Look.load() : Look.classic).cheer;
  if (kind !== "capy" && kind !== "confetti") return;
  const ov = document.createElement("div");
  ov.className = "dl-cheer";
  if (kind === "confetti") {
    const cv = document.createElement("canvas");
    const w = innerWidth, h = innerHeight, k = devicePixelRatio || 1;
    cv.width = w * k; cv.height = h * k;
    ov.appendChild(cv);
    const g = cv.getContext("2d"), css = getComputedStyle(document.documentElement);
    const colors = ["--t-accent", "--t-ok", "--t-warn"].map((v) => css.getPropertyValue(v).trim() || "#888");
    const bits = Array.from({ length: 40 }, () => ({ x0: w * Math.random(), vx: (Math.random() - 0.5) * 120,
      vy: -280 - Math.random() * 260, spin: Math.random() * 8 }));
    const t0 = performance.now();
    const frame = (ts) => {
      const t = Math.min(1, (ts - t0) / 1400);
      g.setTransform(k, 0, 0, k, 0, 0);
      g.clearRect(0, 0, w, h);
      g.globalAlpha = t < 0.8 ? 1 : (1 - t) / 0.2;
      bits.forEach((b, i) => {
        g.save();
        g.translate(b.x0 + b.vx * t, h - 60 + b.vy * t + 520 * t * t);
        g.rotate(b.spin * t);
        g.fillStyle = colors[i % 3];
        g.fillRect(-4, -2, 8, 4);
        g.restore();
      });
      if (t < 1) requestAnimationFrame(frame); else ov.remove();
    };
    requestAnimationFrame(frame);
  } else {
    ov.innerHTML = `<div class="dl-cheer-capy">${capy("joy", 84, "var(--ok)")}</div>`;
    setTimeout(() => ov.remove(), 1400);
  }
  document.body.appendChild(ov);
}
if (!window.cheer) window.cheer = dlCheer;

// ── Листы: общие кусочки ──
/** Поле выбора даты/времени поверх плитки: на iPhone нажатие сразу открывает
 *  системный выбор (как showDatePicker / showTimePicker). */
function dlPickInput(type, value, { min = "", max = "", act = "" } = {}) {
  return `<input class="dl-native" type="${type}" value="${esc(value)}"${min ? ` min="${min}"` : ""}${max ? ` max="${max}"` : ""} data-pick="${act}" aria-label="Выбрать">`;
}
function dlBindPickers(body, onPick) {
  body.addEventListener("click", (e) => {
    const inp = e.target.closest("input.dl-native");
    if (inp) { tick(); try { inp.showPicker && inp.showPicker(); } catch (er) {} }
  });
  body.addEventListener("change", (e) => {
    const inp = e.target.closest("input.dl-native");
    if (inp && inp.value) onPick(inp.dataset.pick, inp.value, inp);
  });
}
function dlTile(ic, text, picker) {
  return `<div class="tile dl-pick">${icon(ic, ic === "calendar_today" ? "o" : "", "font-size:18px;color:var(--accent)")}
    <span class="bd b6 grow" style="--sz:15px">${esc(text)}</span>${picker}</div>`;
}

// ── Новый срок / изменить (DeadlineEditSheet) ──
/** Быстрые даты: Сегодня, Завтра, ближайший понедельник (или пятница) и Через неделю. */
function dlQuickDates(t = now()) {
  const today = isoDay(t), wd = msk(t).wd;
  const ahead = (dow) => (dow - wd + 7) % 7 || 7;
  let mon = ahead(0);
  if (mon === 1 || mon === 7) mon = ahead(4);
  const m = addDays(today, mon), mm = msk(new Date(m + "T12:00:00+03:00"));
  return [
    { label: "Сегодня", date: today },
    { label: "Завтра", date: addDays(today, 1) },
    { label: `${WD_SHORT[mm.wd]}, ${mm.d} ${MONTHS_SHORT[mm.m - 1]}`, date: m },
    { label: "Через неделю", date: addDays(today, 7) },
  ];
}
function dlDateText(iso) {
  const t = msk(new Date(iso + "T12:00:00+03:00"));
  return `${WD_SHORT[t.wd]}, ${t.d} ${MONTHS[t.m - 1]}`;
}
/** Лист срока: без d — новый личный, с ним — правка. → true — сохранено. */
function dlEditSheet(d = null) {
  const x = d ? d.x : null, editing = !!d;
  const t = now();
  let date = d ? (d.dueDate || isoDay(t)) : addDays(isoDay(t), 7);
  let time = d ? (/^\d\d?:\d\d$/.test(d.dueTime) ? d.dueTime : null) : "23:59";
  let error = null, busy = false;
  const hint = !d ? "Личный — видишь только ты. Общие сроки группы добавляет староста."
    : x.personal ? "Личный — видишь только ты."
    : x.editScope === "all" ? "Общий срок — изменится у всей группы. Синк СДО его больше не перезапишет."
    : "Изменится только у тебя — у группы останется как было.";
  const group = x && x.editScope === "all" && !x.personal;
  const y = msk(t).y;
  return Sheet.show(`<div class="ttl" style="--sz:24px">${editing ? "Изменить срок" : "Новый срок"}</div>
    <div class="row" style="align-items:flex-start;gap:var(--s);margin-top:var(--s)">${icon(group ? "groups" : "person_outline", "o", "font-size:18px;color:var(--muted)")}
      <div class="bd mut grow" style="--sz:13px">${esc(hint)}</div></div>
    <div style="height:var(--l)"></div>
    <input class="field dl-field dl-subj" type="text" placeholder="Что сдать" value="${esc(d ? d.subject : "")}" autocapitalize="sentences">
    <div class="eyebrow" style="margin-top:var(--l)">Когда</div>
    <div class="dl-chips"></div>
    <div class="dl-picks"></div>
    <textarea class="field dl-field dl-desc" rows="2" placeholder="Подробности — по желанию" autocapitalize="sentences">${esc(x ? x.description : "")}</textarea>
    <div class="dl-err"></div>
    <button class="btn primary dl-btn50" data-act="save">${editing ? "Сохранить" : "Добавить"}</button>`, (body, close) => {
    const draw = () => {
      body.querySelector(".dl-chips").innerHTML = dlQuickDates().map((q) =>
        `<button class="dl-chip${q.date === date ? " on" : ""}" data-act="quick" data-d="${q.date}">${esc(q.label)}</button>`).join("");
      body.querySelector(".dl-picks").innerHTML = `<div class="dl-two">
        ${dlTile("calendar_today", dlDateText(date), dlPickInput("date", date, { min: `${y - 1}-01-01`, max: `${y + 2}-01-01`, act: "date" }))}
        ${dlTile("schedule", time || "без времени", dlPickInput("time", time || "23:59", { act: "time" }))}</div>`;
      body.querySelector(".dl-err").innerHTML = error ? `<div class="bd" style="--sz:14px;color:var(--danger);margin-top:var(--m)">${esc(error)}</div>` : "";
      body.querySelector("[data-act=save]").disabled = busy;
    };
    draw();
    const subj = body.querySelector(".dl-subj"), desc = body.querySelector(".dl-desc");
    if (!editing) setTimeout(() => subj.focus(), 300);
    desc.addEventListener("input", () => { desc.style.height = "auto"; desc.style.height = Math.min(desc.scrollHeight + 2, 150) + "px"; });
    dlBindPickers(body, (what, v) => { if (what === "date") date = v; else time = v; draw(); });
    on(body, {
      quick(b) { tick(); date = b.dataset.d; draw(); },
      async save() {
        const subject = subj.value.trim();
        if (!subject) { error = "Напиши, что сдать"; draw(); return; }
        tick();
        busy = true; error = null; draw();
        const payload = { subject, due_date: date, due_time: time || "", description: desc.value.trim() };
        try {
          if (!d) await Api.post("/deadlines", payload);
          else await Api.patch(`/deadlines/${d.id}`, payload);
          close(true);
          return;
        } catch (e) {
          error = e.status ? e.message : "Нет интернета — не сохранилось.";
        }
        busy = false; draw();
      },
    });
  }).then((v) => v === true);
}

// ── Действия со сроком (_ActionsSheet) ──
function dlActionsSheet(d) {
  const x = d.x;
  const act = (a, ic, text, color = "", variant = "") => `<button class="dl-act" data-act="pick" data-a="${a}">
    ${icon(ic, variant, `color:${color || "var(--accent)"}`)}<span class="bd b6" style="--sz:16px${color ? `;color:${color}` : ""}">${esc(text)}</span></button>`;
  let acts = "";
  if (d.canSubmit && !d.done) acts += act("submit", "upload", "Сдать файлом");
  if (x.isLink) acts += act("task", "open_in_new", "Задание в СДО");
  if (!d.done) acts += act("remind", "notifications_none", "Напомнить");
  acts += d.done ? act("undone", "undo", "Вернуть в активные") : act("done", "check", "Уже сдал");
  if (x.canEdit) acts += act("edit", "edit", "Изменить", "", "o");
  if (x.mineChanged) acts += act("resetMine", "restart_alt", "Как у всех");
  if (x.canEdit) acts += act("delete", "delete_outline", x.editScope === "me" ? "Убрать у себя" : "Удалить", "var(--danger)");
  if (x.reportable) acts += act("report", "flag", "Пожаловаться или скрыть", "var(--muted)", "o");
  return Sheet.show(`<div class="eyebrow">${esc(d.done ? "сдано" : "до " + dlDueLabel(d))}</div>
    <div class="nm" style="--sz:20px;margin-top:4px">${esc(d.subject)}</div>
    ${x.description && !x.isLink ? `<div class="bd mut" style="--sz:14px;margin-top:var(--s);white-space:pre-wrap">${esc(x.description)}</div>` : ""}
    ${dlHasChips(x, Theme.design2 && !d.done) ? `<div style="margin-top:var(--m)">${dlChips(x, !d.done)}</div>` : ""}
    <div style="height:var(--s)"></div>${acts}`, (body, close) => on(body, { pick: (b) => { tick(); close(b.dataset.a); } }));
}
function dlConfirmDelete(x) {
  return confirmSheet({
    title: x.editScope === "me" ? "Убрать у себя?" : "Удалить срок?",
    text: x.editScope === "me" ? "У группы этот срок останется." : "Вернуть его не получится.",
    action: "Убрать", cancel: "Оставить", danger: true,
  });
}

// ── Напомнить (RemindSheet) ──
function dlRemindSheet(d) {
  const list = [...d.x.reminders];
  let error = null;
  const t = now(), today = isoDay(t);
  const dueDay = d.dueDate || today;
  const start = d.due > t ? dueDay : today;
  return Sheet.show(`<div class="ttl" style="--sz:24px">Напомнить</div>
    <div class="bd mut" style="--sz:14px;margin-top:4px">${esc(d.subject)} — до ${esc(dlDueLabel(d))}</div>
    <div style="height:var(--l)"></div><div class="dl-rlist"></div>
    <div class="dl-chips" style="margin-top:0">
      <button class="dl-chip" data-act="preset" data-p="1d">за день</button>
      <button class="dl-chip" data-act="preset" data-p="3h">за 3 часа</button>
      <button class="dl-chip" data-act="preset" data-p="1h">за час</button>
      <span class="dl-chip dl-chip-own">${icon("edit_calendar", "o", "font-size:16px;color:var(--accent)")}своё время
        ${dlPickInput("datetime-local", `${start}T09:00`, { min: `${today}T00:00`, max: `${addDays(dueDay, 1)}T23:59`, act: "own" })}</span>
    </div>
    <div class="bd mut" style="--sz:12px;margin-top:var(--s)">Своё время — по Москве.</div>
    <div class="dl-err"></div>
    <div style="height:var(--l)"></div>
    <button class="btn outline dl-done-btn" data-act="ok">Готово</button>`, (body, close) => {
    const draw = () => {
      body.querySelector(".dl-rlist").innerHTML = list.map((r, i) => `<div class="tile dl-rem">
        ${icon("notifications_active", "o", "font-size:18px;color:var(--warn)")}<span class="bd b6 grow" style="--sz:15px">${esc(r.label)}</span>
        <button class="dl-ib" data-act="rm" data-k="${i}" aria-label="Убрать напоминание">${icon("close", "", "font-size:18px;color:var(--muted)")}</button></div>`).join("");
      body.querySelector(".dl-err").innerHTML = error ? `<div class="bd" style="--sz:14px;color:var(--danger);margin-top:var(--m)">${esc(error)}</div>` : "";
    };
    const add = async (payload) => {
      tick();
      error = null; draw();
      try {
        const r = await Api.post(`/deadlines/${d.id}/remind`, payload);
        list.push({ at: String(r.at), label: String(r.label) });
        list.sort((a, b) => a.at.localeCompare(b.at));
      } catch (e) { error = errorText(e); }
      draw();
    };
    draw();
    dlBindPickers(body, (what, v, inp) => { if (what === "own") { add({ at: v.slice(0, 16) }); inp.value = `${start}T09:00`; } });
    on(body, {
      preset: (b) => add({ preset: b.dataset.p }),
      async rm(b) {
        tick();
        const r = list[+b.dataset.k];
        if (!r) return;
        try {
          await Api.del(`/deadlines/${d.id}/remind?at=${encodeURIComponent(r.at)}`);
          list.splice(list.indexOf(r), 1);
        } catch (e) { error = errorText(e); }
        draw();
      },
      ok: () => close(),
    });
  });
}

// ── «Сдать файлом» (SubmitSheet) ──
function dlRules(j) {
  const r = {
    accepted: (j.accepted || []).map((a) => String(a).toLowerCase()), labels: (j.labels || []).map(String),
    maxFiles: typeof j.maxfiles === "number" ? Math.trunc(j.maxfiles) : 3, maxBytes: typeof j.maxbytes === "number" ? Math.trunc(j.maxbytes) : 0,
    closed: typeof j.closed === "string" ? j.closed : null,
  };
  r.perSubmit = r.maxFiles <= 0 ? 3 : Math.min(r.maxFiles, 3);
  r.fits = (name) => !r.accepted.length || r.accepted.some((e) => name.toLowerCase().endsWith(e));
  r.limit = `${(r.maxBytes / 1048576).toFixed(r.maxBytes >= 10485760 ? 0 : 1)} МБ`;
  r.describe = () => [r.labels.length ? r.labels.join(", ") : r.accepted.length ? r.accepted.join(" ") : "любые файлы",
    `до ${r.perSubmit} ${plural(r.perSubmit, "файла", "файлов", "файлов")}`, r.maxBytes > 0 ? `до ${r.limit}` : ""].filter(Boolean).join(" · ");
  r.problem = (f) => {
    if (!r.fits(f.name)) {
      const dot = f.name.lastIndexOf(".");
      const what = dot > 0 ? f.name.slice(dot).toLowerCase() : "Файл без расширения";
      return `${what} задание не примет — нужно ${r.labels.length ? r.labels.join(", ") : r.accepted.join(", ")}`;
    }
    if (r.maxBytes > 0 && f.size > r.maxBytes) return `больше ${r.limit} — задание не примет`;
    return null;
  };
  return r;
}
function dlFileSize(bytes) {
  if (bytes < 1048576) return `${Math.ceil(bytes / 1024)} КБ`;
  const mb = bytes / 1048576;
  return `${mb.toFixed(mb >= 10 ? 0 : 1).replace(".", ",")} МБ`;
}
function dlReadFile(file) {
  return new Promise((resolve, reject) => {
    const fr = new FileReader();
    fr.onload = () => resolve({ name: file.name, size: file.size, data: String(fr.result).replace(/^data:[^,]*,/, "") });
    fr.onerror = () => reject(fr.error);
    fr.readAsDataURL(file);
  });
}
/** Лист сдачи: задание по сроку (deadlineId) или из работ предмета (cmid).
 *  replace — «Редактировать ответ». → true — сдано. */
function dlSubmitSheet({ title, deadlineId = 0, cmid = 0, replace = false }) {
  return Sheet.show(`<div class="dl-sub"></div>`, (body, close) => {
    let rules = null, error = null, done = null, sending = false;
    const files = [];   // {f, why}
    const d2 = Theme.design2;
    const good = () => files.filter((e) => !e.why).map((e) => e.f);
    const verb = replace ? "Заменить" : "Сдать";
    const fileRow = (e, i) => {
      const bad = !!e.why;
      if (!d2) return `<div class="tile dl-frow">${icon("insert_drive_file", "o", "font-size:18px;color:var(--accent)")}
        <span class="bd b6 grow" style="--sz:14px">${esc(e.f.name)}</span><span class="bd mut" style="--sz:12px">${Math.ceil(e.f.size / 1024)} КБ</span>
        <button class="dl-ib" data-act="rm" data-k="${i}" aria-label="Убрать">${icon("close", "", "font-size:18px;color:var(--muted)")}</button></div>`;
      return `<div class="tile dl-frow">${icon("insert_drive_file", "o", `font-size:18px;color:${bad ? "var(--danger)" : "var(--accent)"}`)}
        <div class="grow"><div class="bd b6" style="--sz:14px;word-break:break-word">${esc(e.f.name)}</div>
        ${bad ? `<div class="bd" style="--sz:12px;color:var(--danger);margin-top:2px">${esc(e.why)}</div>` : ""}</div>
        <span class="bd mut" style="--sz:12px">${dlFileSize(e.f.size)}</span>
        ${bad ? icon("priority_high", "", "font-size:18px;color:var(--danger)") : icon("check", "", "font-size:18px;color:var(--ok)")}
        <button class="dl-ib" data-act="rm" data-k="${i}" aria-label="Убрать">${icon("close", "", "font-size:18px;color:var(--muted)")}</button></div>`;
    };
    const draw = () => {
      const box = body.querySelector(".dl-sub");
      if (done != null) {
        box.innerHTML = `<div class="dl-donebox"><div class="dl-hop">${capy("joy", 104, "var(--ok)")}
          <span class="dl-hopcheck">${icon("check", "", "font-size:22px")}</span></div>
          <div class="ttl" style="--sz:28px;margin-top:var(--l)">Сдано</div>
          <div class="bd mut" style="--sz:14px;margin-top:var(--s);text-align:center">${esc(done)}</div>
          <button class="btn dl-okbtn" data-act="close">Отлично</button></div>`;
        return;
      }
      const n = good().length;
      let mid = "";
      if (!rules && !error) mid = `<div class="spinner" style="margin:var(--s) auto;width:36px;height:36px"></div>`;
      else if (rules && rules.closed != null) mid = `<div class="bd" style="--sz:15px;color:var(--danger)">${esc(rules.closed)}</div>`;
      else if (rules) {
        const more = d2 ? n < rules.perSubmit && files.length < rules.perSubmit + 3 : files.length < rules.perSubmit;
        const accept = rules.accepted.join(",");
        mid = `<div class="row" style="gap:var(--s)">${icon("rule", "", "font-size:18px;color:var(--muted)")}<span class="bd mut grow" style="--sz:14px">Принимает: ${esc(rules.describe())}</span></div>
          ${replace ? `<div class="row" style="gap:var(--s);margin-top:var(--s)">${icon("swap_horiz", "", "font-size:18px;color:var(--muted)")}<span class="bd mut grow" style="--sz:14px">Новые файлы заменят прежние</span></div>` : ""}
          <div style="height:var(--m)"></div>${files.map(fileRow).join("")}
          ${more ? `<label class="dl-obtn${sending ? " off" : ""}">${icon("attach_file", "", "font-size:18px")}${files.length ? "Ещё файл" : "Выбрать файл"}
            <input type="file" class="dl-file"${accept ? ` accept="${esc(accept)}"` : ""}${sending ? " disabled" : ""}></label>` : ""}`;
      }
      box.innerHTML = `<div class="eyebrow">${replace ? "Редактировать ответ" : "Сдать файлом"}</div>
        <div class="nm" style="--sz:20px;margin-top:4px">${esc(title)}</div><div style="height:var(--l)"></div>${mid}
        ${error ? `<div class="bd" style="--sz:14px;color:var(--danger);margin-top:var(--m)">${esc(error)}</div>` : ""}
        <button class="btn primary dl-btn50" data-act="send"${n === 0 || sending ? " disabled" : ""}>
          ${sending ? '<span class="dl-mini"></span>' : icon("upload")}${sending ? "Отправляю…" : d2 && n > 0 ? `${verb} ${n} ${plural(n, "файл", "файла", "файлов")}` : verb}</button>`;
    };
    body.addEventListener("change", async (e) => {
      const inp = e.target.closest("input.dl-file");
      if (!inp || !inp.files || !rules) return;
      tick();
      const got = [];
      try { for (const f of inp.files) got.push(await dlReadFile(f)); } catch (er) { error = errorText(er); draw(); return; }
      if (d2) {
        for (const f of got) {
          const why = rules.problem(f);
          if (why == null ? good().length < rules.perSubmit : files.length < rules.perSubmit + 3) files.push({ f, why });
        }
        error = null;
      } else {
        const bad = got.filter((f) => !rules.fits(f.name)).map((f) => f.name);
        const big = rules.maxBytes > 0 ? got.filter((f) => f.size > rules.maxBytes).map((f) => f.name) : [];
        for (const f of got) if (!bad.includes(f.name) && !big.includes(f.name) && files.length < rules.perSubmit) files.push({ f, why: null });
        error = bad.length ? `Задание не примет: ${bad.join(", ")} — нужно ${rules.labels.length ? rules.labels.join(", ") : rules.accepted.join(" ")}`
          : big.length ? `Слишком большой: ${big.join(", ")}` : null;
      }
      draw();
    });
    on(body, {
      rm(b) { files.splice(+b.dataset.k, 1); draw(); },
      close: () => close(true),
      async send() {
        if (sending || !good().length) return;
        tick();
        sending = true; error = null; draw();
        try {
          const r = await Api.post("/sdo/submit", { deadline_id: deadlineId, cmid, ...(replace ? { replace: true } : {}),
            files: good().map((f) => ({ name: f.name, data: f.data })) });
          try { navigator.vibrate && navigator.vibrate(18); } catch (er) {}
          done = r && typeof r.status === "string" ? r.status : "Отправлено в СДО";
        } catch (e) { error = e.status ? e.message : "Нет интернета — файл не ушёл."; }
        sending = false; draw();
      },
    });
    draw();
    Api.get(`/sdo/submit-rules?cmid=${cmid}&deadline_id=${deadlineId}`)
      .then((r) => { rules = dlRules(r || {}); draw(); })
      .catch((e) => { error = errorText(e); draw(); });
  }).then((v) => v === true);
}
window.dlSubmitSheet = dlSubmitSheet;

// ── «⋯» у чужой записи: пожаловаться или скрыть автора (widgets/report.dart) ──
const DL_REASONS = ["Оскорбление или травля", "Спам или реклама", "Чужие личные данные", "Другое"];
/** Кнопка «⋯» (ReportButton): data-act="report" data-kind data-id. */
function dlReportButton(kind, id) {
  return `<button class="dl-ib" data-act="report" data-kind="${kind}" data-id="${id}" aria-label="Пожаловаться или скрыть">${icon("more_horiz", "", "font-size:20px;color:var(--muted)")}</button>`;
}
async function openReportMenu(kind, id, onChanged) {
  tick();
  const choice = await Sheet.show(`<div class="ttl" style="--sz:24px">Пожаловаться</div>
    <div class="bd mut" style="--sz:15px;margin-top:var(--s)">Что не так с записью? Посмотрим и уберём, если нарушает правила.</div>
    <div style="height:var(--s)"></div>
    ${DL_REASONS.map((r, i) => `<button class="dl-rrow" data-act="pick" data-k="${i}"><span class="bd" style="--sz:16px">${esc(r)}</span></button>`).join("")}
    <div class="divider" style="margin:var(--s) 0"></div>
    <button class="dl-rrow" data-act="hide">${icon("visibility_off", "o", "font-size:20px;color:var(--muted)")}<span class="bd" style="--sz:16px">Скрыть автора</span></button>
    <button class="dl-rules" data-act="rules">Правила Капибары</button>`, (body, close) => on(body, {
    pick: (b) => close(DL_REASONS[+b.dataset.k]),
    hide: () => close("__hide"),
    rules: () => (window.openLegal ? openLegal("rules") : toast("Скоро")),
  }));
  if (!choice) return;
  try {
    if (choice === "__hide") {
      const ok = await confirmSheet({ title: "Скрыть автора?",
        text: "Его заметки, ДЗ и файлы пропадут у тебя. У остальных всё останется. Вернуть — «Ещё → Безопасность».", action: "Скрыть" });
      if (!ok) return;
      await Api.post("/hide-author", { kind, id });
      toast("Скрыл — его записей у тебя больше нет", "done");
      if (onChanged) onChanged();
    } else {
      await Api.post("/report", { kind, id, reason: choice });
      toast("Спасибо! Посмотрим и уберём, если нарушает правила", "done");
    }
  } catch (e) { toast(errorText(e), "error"); }
}
window.openReportMenu = openReportMenu;

// ── Вкладка «Сдать» ──
Screens.deadlines = {
  mount(body, screen) {
    let data = null, error = null, showDone = false, rows = {};

    const load = async (fromCache = false) => {
      const j = fromCache ? Api.cached("/deadlines?include_done=true") : await Api.get("/deadlines?include_done=true");
      if (!j || !Array.isArray(j.items)) return null;
      return { list: j.items.map(dlOf), sdo: dlSdo(j.sdo) };
    };
    const reload = async () => {
      try { data = await load(); error = null; }
      catch (e) { error = e; }
      draw();
    };

    const row = (d, at, late) => {
      rows[d.id] = d;
      const name = dlSplit(d.subject), t = msk(d.due), past = d.done || late, n = dlDays(at, d.due);
      const color = past ? "var(--muted)" : n === 0 ? "var(--danger)" : n === 1 ? "var(--warn)" : "var(--text)";
      return `<div class="dl-sw" data-id="${d.id}"><div class="dl-swbg" style="background:${d.done ? "var(--muted)" : "var(--ok)"}">
          <span class="bd b7" style="--sz:15px;color:#fff">${d.done ? "Вернуть" : "Сдано"}</span></div>
        <button class="dl-row${d.done ? " done" : ""}" data-act="open" data-id="${d.id}">
          <div class="dl-date"><div class="bd mut" style="--sz:12px">${past ? MONTHS_SHORT[t.m - 1] : WD_SHORT[t.wd].toLowerCase()}</div>
            <div class="num" style="--sz:22px;color:${color}">${t.d}</div></div>
          <div class="grow"><div class="nm" style="--sz:15px${d.done ? ";color:var(--muted)" : ""}">${esc(name.task)}</div>
            ${name.course || !d.done ? `<div style="margin-top:2px">${dlSubjectLine(name.course, d.done ? "" : dlTime(d))}</div>` : ""}
            ${dlHasChips(d.x, Theme.design2 && !d.done) ? `<div style="margin-top:6px">${dlChips(d.x, !d.done)}</div>` : ""}</div>
          ${d.done ? icon("check", "", "font-size:20px;color:var(--ok);margin-left:var(--s)") : ""}
        </button></div>`;
    };
    const card = (list, at, late = false) => `<div class="hx"><div class="tile p0">${list.map((d, i) =>
      (i ? '<div class="divider"></div>' : "") + row(d, at, late)).join("")}</div></div>`;

    const hot = (d, at) => {
      rows[d.id] = d;
      const left = d.due - at, h = Math.floor(left / 3600000), m = Math.floor(left / 60000) % 60;
      const when = dlDays(at, d.due) === 0 ? `до ${dlTime(d)}` : `завтра до ${dlTime(d)}`;
      const name = dlSplit(d.subject);
      const unit = (u) => `<span class="bd mut dl-unit">${u}</span>`;
      const big = (v) => `<span class="num" style="--sz:44px;color:var(--danger)">${v}</span>`;
      return `<div class="hx"><div class="tile dl-hot" data-act="open" data-id="${d.id}" role="button" tabindex="0">
        <div class="row" style="gap:6px"><i class="cm-dot" style="width:8px;height:8px;background:var(--danger)"></i>
          <span class="eyebrow" style="color:var(--danger)">горит · ${esc(when)}</span></div>
        <div class="nm" style="--sz:19px;margin-top:var(--s)">${esc(name.task)}</div>
        ${name.course ? `<div style="margin-top:4px">${dlSubjectLine(name.course, "", 14)}</div>` : ""}
        ${dlHasChips(d.x, Theme.design2 && !d.done) ? `<div style="margin-top:var(--s)">${dlChips(d.x)}</div>` : ""}
        <div class="row" style="align-items:flex-end;margin-top:var(--m)">
          <div class="grow dl-count">${h > 0 ? big(h) + unit("ч") : ""}${big(h > 0 ? String(m).padStart(2, "0") : m)}${unit("мин")}</div>
          <button class="dl-hotbtn" data-act="${d.canSubmit ? "submit" : "doneHot"}" data-id="${d.id}">
            ${icon(d.canSubmit ? "upload" : "check", "", "font-size:18px")}${d.canSubmit ? "Сдать" : "Уже сдал"}</button>
        </div></div></div>`;
    };

    const draw = () => {
      if (!data) {
        body.innerHTML = error ? '<div style="height:120px"></div>' + notice("Не загрузилось", errorText(error), { pose: "sad", retry: "retry" }) : spinner();
        return;
      }
      rows = {};
      const t = now(), items = data.list;
      const sdo = Theme.design2 ? data.sdo : null, sdoDown = !!sdo && !sdo.ok;
      const open = items.filter((d) => !d.done && d.due > t).sort((a, b) => a.due - b.due);
      const late = items.filter((d) => !d.done && !(d.due > t)).sort((a, b) => b.due - a.due);
      const done = items.filter((d) => d.done).sort((a, b) => b.due - a.due);
      const burning = open.length && !open[0].done && open[0].due > t && open[0].due - t < 864e5 ? open[0] : null;
      const weeks = new Map();
      for (const d of open) {
        if (d === burning) continue;
        const k = mondayOf(d.due);
        if (!weeks.has(k)) weeks.set(k, []);
        weeks.get(k).push(d);
      }
      let html = screenTitle("Сдать", { trailing: `<button class="dl-fab" data-act="add" aria-label="Свой срок">${icon("add")}</button>` });
      html += `<div class="dl-entries"><button class="tile dl-entry" data-act="hw">${icon("assignment", "o", "font-size:20px;color:var(--accent)")}
          <span class="bd b6 grow ell" style="--sz:15px">ДЗ группы</span>${icon("chevron_right", "", "font-size:20px;color:var(--muted)")}</button>
        <button class="tile dl-entry" data-act="notes">${icon("push_pin", "o", "font-size:20px;color:var(--accent)")}
          <span class="bd b6 grow ell" style="--sz:15px">Заметки</span>${icon("chevron_right", "", "font-size:20px;color:var(--muted)")}</button></div>`;
      html += `<div class="dl-segwrap"><div class="dl-seg">
        <button class="${showDone ? "" : "on"}" data-act="seg" data-k="0" aria-pressed="${!showDone}">Впереди · ${open.length}</button>
        <button class="${showDone ? "on" : ""}" data-act="seg" data-k="1" aria-pressed="${showDone}">Сдано · ${done.length}</button></div></div>`;
      if (!showDone) {
        if (sdoDown && open.length) {
          html += `<div class="dl-sdowrap"><div class="tile dl-sdo">${capy("sad", 44, "var(--muted)")}
            <div class="grow"><div class="bd b6" style="--sz:15px">СДО не ответил</div>
            <div class="bd mut" style="--sz:13px;margin-top:2px">${esc(dlSdoShown(sdo.lastOk, t))}</div>
            <button class="dl-retry" data-act="retrySdo">Попробовать ещё раз</button></div></div></div>`;
        }
        if (burning) html += hot(burning, t);
        if (!open.length && sdoDown) html += notice("СДО не ответил", dlSdoShown(sdo.lastOk, t), { pose: "sad", retry: "retrySdo", retryLabel: "Попробовать ещё раз" });
        else if (!open.length && Theme.design2) html += notice("Ближайших сроков нет",
          sdo && sdo.checkedAt ? dlSdoChecked(sdo.checkedAt, t) : "Новые задания из СДО появятся здесь сами. Свой срок — кнопкой +.", { pose: "joy" });
        else if (!open.length) html += notice(late.length ? "Новых сроков нет" : "Всё сдано", "Новые задания из СДО появятся здесь сами. Свой срок — кнопкой +.", { pose: "joy" });
        for (const [k, list] of weeks) html += section(dlWeekLabel(k, t)) + card(list, t);
        if (late.length) html += section(`Срок прошёл · ${late.length}`) + card(late, t, true);
      } else if (!done.length) html += notice("Пока ничего", "Сданное появится здесь — свайп вправо по сроку или «Уже сдал».");
      else html += card(done, t);
      body.innerHTML = html + '<div style="height:120px"></div>';
    };

    const run = async (call) => {
      try { await call(); return true; } catch (e) { toast(errorText(e), "error"); return false; }
    };
    const toggle = async (d, isDone) => {
      const ok = await run(() => Api.post(`/deadlines/${d.id}/toggle`, { done: isDone }));
      if (ok && isDone) dlCheer();
    };
    const submit = async (d) => { if (await dlSubmitSheet({ title: d.subject, deadlineId: d.id })) await reload(); };
    const actions = async (d) => {
      const a = await dlActionsSheet(d);
      if (!a) return;
      switch (a) {
        case "submit": await submit(d); break;
        case "task": openLink(d.x.description); break;
        case "remind": await dlRemindSheet(d); await reload(); break;
        case "done": case "undone": await toggle(d, a === "done"); await reload(); break;
        case "edit":
          if (await dlEditSheet(d)) {
            toast(d.x.editScope === "me" && !d.x.personal ? "Сохранено у тебя" : "Сохранено", "done");
            await reload();
          }
          break;
        case "delete":
          if (!(await dlConfirmDelete(d.x))) return;
          if (await run(() => Api.del(`/deadlines/${d.id}`))) await reload();
          break;
        case "resetMine":
          if (await run(() => Api.del(`/deadlines/${d.id}/mine`))) { toast("Снова как у всей группы", "done"); await reload(); }
          break;
        case "report": await openReportMenu("deadline", d.id, reload); break;
      }
    };

    on(body, {
      retry() { error = null; body.innerHTML = spinner(); reload(); },
      async retrySdo() {
        tick();
        await reload();
        if (data && data.sdo && data.sdo.ok === false && Theme.design2) toast("СДО пока молчит — бот проверит его сам", "info");
      },
      async add() {
        tick();
        if (await dlEditSheet()) { toast("Срок добавлен — видишь только ты", "done"); await reload(); }
      },
      hw: () => { tick(); window.openHomework ? openHomework() : toast("Скоро"); },
      notes: () => { tick(); window.openNotes ? openNotes() : toast("Скоро"); },
      seg(b) {
        const v = b.dataset.k === "1";
        if (v === showDone) return;
        tick(); showDone = v; draw();
      },
      open(b) {
        if (swiped) return;
        const d = rows[b.dataset.id];
        if (d) { tick(); actions(d); }
      },
      submit(b, e) { e.stopPropagation(); tick(); const d = rows[b.dataset.id]; if (d) submit(d); },
      async doneHot(b, e) { e.stopPropagation(); tick(); const d = rows[b.dataset.id]; if (d) { await toggle(d, true); await reload(); } },
    });

    // Свайп вправо по строке (Dismissible): дальше 40 % ширины — «сдал»/«вернуть»,
    // строка возвращается на место, список перечитывается.
    let sw = null, swiped = false;
    body.addEventListener("touchstart", (e) => {
      const el = e.target.closest(".dl-sw");
      if (!el || e.touches.length > 1) return;
      const p = e.touches[0];
      sw = { el, fg: el.querySelector(".dl-row"), x: p.clientX, y: p.clientY, dx: 0, on: false };
    }, { passive: true });
    body.addEventListener("touchmove", (e) => {
      if (!sw) return;
      const p = e.touches[0], dx = p.clientX - sw.x, dy = p.clientY - sw.y;
      if (!sw.on) {
        if (Math.abs(dy) > 10 && Math.abs(dy) > Math.abs(dx)) { sw = null; return; }
        if (dx > 10 && dx > Math.abs(dy)) { sw.on = true; sw.el.classList.add("moving"); }
        else return;
      }
      sw.dx = Math.max(0, dx - 10);
      sw.fg.style.transform = `translateX(${sw.dx}px)`;
    }, { passive: true });
    const endSwipe = async () => {
      if (!sw) return;
      const s = sw;
      sw = null;
      if (!s.on) return;
      swiped = true;
      setTimeout(() => (swiped = false), 350);
      const fire = s.dx > s.el.clientWidth * 0.4;
      s.fg.style.transition = "transform .22s cubic-bezier(.2,.8,.2,1)";
      s.fg.style.transform = "";
      setTimeout(() => { s.fg.style.transition = ""; s.el.classList.remove("moving"); }, 240);
      const d = rows[s.el.dataset.id];
      if (fire && d) { tick(); await toggle(d, !d.done); await reload(); }
    };
    body.addEventListener("touchend", endSwipe);
    body.addEventListener("touchcancel", endSwipe);

    // сразу — из запаса телефона, свежие следом (Loader)
    try { const c = Api.cached("/deadlines?include_done=true"); if (c && Array.isArray(c.items)) data = { list: c.items.map(dlOf), sdo: dlSdo(c.sdo) }; } catch (e) {}
    draw();
    reload();
    const timer = setInterval(() => { if (data && !sw) draw(); }, 30000);
    screen.reload = reload;
    pullRefresh(screen, reload);
    return () => clearInterval(timer);
  },
  onShow(body, screen) { if (screen.reload) screen.reload(); },
};

// ── Экран задания СДО (task.dart) ──
function dlHumanStatus(s) {
  const rules = [[/не представлен|нет ответа|no attempt/i, "Ещё не сдано"], [/черновик|draft/i, "Черновик — не отправлен"],
    [/отправлено для оценивания|submitted for grading/i, "Сдано, ждёт оценки"], [/вне сайта/i, "Сдаётся на занятии"]];
  for (const [re, text] of rules) if (re.test(s)) return text;
  return s;
}
const DL_TAGS = { ok: ["check_circle", "зачтено"], low: ["error_outline", "ниже порога"], wait: ["hourglass_top", "ждёт оценки"],
  offline: ["groups", "сдаётся на занятии"], soon: ["lock", "ещё закрыто"], miss: ["cancel", "срок прошёл"], late: ["hourglass_top", "ждём оценку"] };
const DL_TAG_OUTLINED = new Set(["groups", "lock", "cancel"]);
function dlFileIcon(name) {
  const ext = name.includes(".") ? name.split(".").pop().toLowerCase() : "";
  if (ext === "pdf") return "picture_as_pdf";
  if (["doc", "docx", "odt", "rtf", "txt"].includes(ext)) return "description";
  if (["xls", "xlsx", "csv"].includes(ext)) return "table_chart";
  if (["ppt", "pptx"].includes(ext)) return "slideshow";
  if (["zip", "rar", "7z"].includes(ext)) return "folder_zip";
  if (["png", "jpg", "jpeg"].includes(ext)) return "image";
  return "insert_drive_file";
}
/** Ссылка на файл из СДО (/sdl/…): полный адрес или путь на этом сервере. */
function dlSdoLink(dl) { return /^http/.test(dl) ? dl : location.origin + dl; }
function dlNeedsSdo(msg) { return /подключи|устарел/.test(msg); }

/** Экран задания: work — работа из журнала (name, module, cmid, status, grade, max, pass_mark, url). */
function openTask(work, course = "") {
  const w = work || {}, quiz = w.module === "quiz";
  Nav.push((body, screen) => {
    let t = null, error = null, loadedAt = 0, back = false;
    const load = async () => {
      try {
        const r = await Api.get(`/sdo/task/${w.cmid}${quiz ? "?module=quiz" : ""}`);
        t = r || {}; error = null; loadedAt = Date.now();
      } catch (e) { error = errorText(e); }
      draw();
    };
    const chip = (text, { ic = "", color = "" } = {}) => `<span class="dl-tchip" style="--c:${color || "var(--muted)"}">
      ${ic ? icon(ic, DL_TAG_OUTLINED.has(ic) ? "o" : "", "font-size:14px;color:var(--c)") : ""}<span class="bd b6" style="--sz:13px;color:${color || "var(--text)"}">${esc(text)}</span></span>`;
    const fileList = (list, mine) => `<div class="hx"><div class="tile p0">${list.map((f, i) => `${i ? '<div class="divider"></div>' : ""}
      <button class="irow dl-tfile" data-act="dl" data-k="${i}" data-mine="${mine ? 1 : 0}">${icon(dlFileIcon(String(f.name)), "o", "font-size:20px;color:var(--accent)")}
        <span class="bd b6 grow" style="--sz:14px">${esc(f.name)}</span>${icon("download", "", "font-size:20px;color:var(--muted)")}</button>`).join("")}</div></div>`;
    const openSdo = (url) => `<div class="hx" style="padding-top:var(--s)"><button class="dl-tlink" data-act="link" data-url="${esc(url)}">
      ${icon("open_in_new", "", "font-size:18px;color:var(--accent)")}<span class="bd b6" style="--sz:15px;color:var(--accent)">Открыть в СДО</span></button></div>`;
    const quizCard = (status) => {
      const attempts = Array.isArray(t.attempts) ? t.attempts : [], allowed = t.attempts_allowed;
      const state = t.open_now === true ? "Тест открыт — можно проходить" : t.no_more === true ? "Попыток больше нет"
        : t.unavailable === true || status === "soon" ? `Ещё не открыт${t.opens != null ? ` · откроется ${t.opens}` : ""}` : "Сейчас пройти нельзя";
      const limit = typeof t.time_limit === "number" ? Math.trunc(t.time_limit) : null;
      const line = (ic, text, bold = false, v = "") => `<div class="row dl-qline">${icon(ic, v, "font-size:18px;color:var(--muted)")}
        <span class="bd grow${bold ? " b6" : ""}" style="--sz:14px">${esc(text)}</span></div>`;
      let out = line(t.open_now === true ? "lock_open" : "lock", state, true, t.open_now === true ? "" : "o");
      out += line("replay", `Попытки: ${allowed != null ? `использовано ${attempts.length} из ${allowed}` : `${attempts.length} · без ограничения`}`);
      if (String(t.best ?? "")) out += line("emoji_events", `Лучший результат: ${String(t.best).replace("/", " из ")}`, false, "o");
      if (String(t.pass_text ?? "")) out += line("flag", `Проходная: ${t.pass_text}`, false, "o");
      if (limit != null && limit > 0) out += line("timer", `На попытку: ${limit % 60 ? `${limit} мин` : `${limit / 60} ч`}`, false, "o");
      attempts.forEach((a, i) => {
        const g = String(a.grade ?? "") ? a.grade : a.state ?? "";
        out += line("check", `Попытка ${i + 1}: ${g}${String(a.finished ?? "") ? ` · ${a.finished}` : ""}`);
      });
      return `<div class="hx"><div class="tile">${out}</div></div>`;
    };
    const content = () => {
      const status = String(w.status ?? ""), files = Array.isArray(t.files) ? t.files : [], mine = Array.isArray(t.mine) ? t.mine : [];
      const remaining = String(t.remaining ?? "").replace(/ осталось$/, "");
      const tag = status === "todo" && remaining ? ["schedule", remaining] : DL_TAGS[status];
      const tagColor = status === "ok" ? "var(--ok)" : status === "low" || status === "miss" ? "var(--danger)" : status === "todo" ? "var(--warn)" : "var(--muted)";
      const graded = status === "ok" || status === "low";
      const limit = typeof t.limit === "number" ? Math.trunc(t.limit) : 1;
      const max = w.max;
      let chips = tag ? chip(tag[1], { ic: tag[0], color: tagColor }) : "";
      if (graded) chips += chip("Оценено");
      else if (String(t.status ?? "")) chips += chip(dlHumanStatus(String(t.status)));
      chips += chip(w.grade != null ? `Оценка ${dlNum(w.grade)} / ${dlNum(max ?? 0)}` : "Не оценено");
      let h = `<div class="hx"><div class="tile" style="border-radius:var(--r-card)">
        ${t.due != null ? `<div class="eyebrow">Срок сдачи</div><div class="ttl" style="--sz:20px;margin-top:2px">${esc(t.due)}</div><div style="height:var(--m)"></div>` : ""}
        <div class="dl-tags" style="gap:6px">${chips}</div>
        ${max != null ? `<div class="bd mut" style="--sz:13px;margin-top:var(--m)">до ${dlNum(max)} ${plural(Math.round(max), "балла", "баллов", "баллов")}${w.pass_mark != null ? ` · зачёт от ${dlNum(w.pass_mark)}` : ""}</div>` : ""}
        ${t.graded_by != null ? `<div class="bd mut" style="--sz:13px;margin-top:4px">Оценил(а): ${esc(t.graded_by)}${t.graded_at != null ? ` · ${esc(t.graded_at)}` : ""}</div>` : ""}
      </div></div>`;
      if (String(t.description ?? "")) h += section("Задание") + `<div class="hx"><div class="tile dl-sel bd" style="--sz:15px">${esc(t.description)}</div></div>`;
      if (String(t.feedback ?? "")) h += section("Комментарий преподавателя") + `<div class="hx"><div class="tile dl-sel bd" style="--sz:15px">${esc(t.feedback)}</div></div>`;
      if (t.quiz === true) h += section("Тест") + quizCard(status);
      if (files.length) h += section("Файлы задания") + fileList(files, false);
      if (mine.length) h += section("Мой ответ") + fileList(mine, true);
      h += '<div style="height:var(--xl)"></div>';
      const big = (act, ic, text, cls = "primary") => `<div class="hx"><button class="btn ${cls} dl-btn50" data-act="${act}">${icon(ic, ic === "edit" ? "o" : "")}${esc(text)}</button></div>`;
      if (t.can_edit === true || t.can_remove === true) {
        if (t.can_edit === true) h += big("edit", "edit", "Редактировать ответ");
        if (t.can_remove === true) h += `<div class="hx" style="padding-top:var(--s)"><button class="btn dl-btn50 dl-dangerline" data-act="remove">${icon("delete_outline")}Удалить ответ</button></div>`;
      } else if (t.can_submit === true) {
        h += big("submit", "upload", `${mine.length ? "Сдать ещё / заменить" : "Сдать работу"}${limit > 1 ? ` · до ${limit} ${plural(limit, "файла", "файлов", "файлов")}` : ""}`);
      } else if (status === "offline") {
        h += `<div class="bd mut" style="--sz:14px;text-align:center;padding:0 var(--xl)">Эту работу сдают на занятии, не через СДО.</div>`;
      }
      if (t.quiz === true && t.open_now === true) h += big("link", "open_in_new", "Пройти тест в СДО").replace('data-act="link"', `data-act="link" data-url="${esc(t.url)}"`);
      else if (typeof t.url === "string") h += openSdo(t.url);
      return h;
    };
    const draw = () => {
      const sub = [course, quiz ? "тест" : ""].filter(Boolean).join(" · ");
      let h = backRow() + screenTitle(String((t && t.title) ?? w.name ?? ""), { sub });
      if (t) h += content();
      else if (error != null) {
        h += notice("Задание не открылось", error, { retry: "retry" });
        if (dlNeedsSdo(error)) h += `<div style="padding:var(--l) var(--l) 0"><button class="btn primary" data-act="connect">Подключить СДО</button></div>`;
        if (typeof w.url === "string") h += openSdo(w.url);
      } else h += `<div style="padding:var(--xxl)">${spinner()}</div>`;
      body.innerHTML = h + '<div style="height:var(--xxl)"></div>';
    };
    const submit = async (replace = false) => {
      tick();
      const ok = await dlSubmitSheet({ title: String(t.title ?? w.name ?? ""), cmid: w.cmid, replace });
      if (ok) await load();
    };
    on(body, {
      retry() { error = null; draw(); load(); },
      async dl(b) {
        tick();
        if (loadedAt && Date.now() - loadedAt > 9 * 60000) await load();   // ссылки живут 10 минут
        if (!t) return;
        const list = (b.dataset.mine === "1" ? t.mine : t.files) || [], f = list[+b.dataset.k];
        if (f) openLink(dlSdoLink(String(f.dl)));
      },
      link(b) { tick(); openLink(b.dataset.url); },
      submit: () => submit(false),
      edit: () => submit(true),
      async remove() {
        const ok = await confirmSheet({ title: "Удалить ответ?", text: "Файлы ответа уберутся из СДО. Сдать заново можно, пока не прошёл срок.",
          action: "Удалить ответ", danger: true });
        if (!ok) return;
        try { await Api.post("/sdo/submission/remove", { cmid: w.cmid }); toast("Ответ удалён", "done"); }
        catch (e) { toast(errorText(e), "error"); return; }
        await load();
      },
      connect() {
        tick();
        if (!window.openSdoConnect) { toast("Скоро"); return; }
        back = true;
        openSdoConnect();
      },
    });
    // вернулись с подключения СДО — задание заново
    screen.onShow = () => { if (back) { back = false; error = null; draw(); load(); } };
    draw();
    load();
  }, { tint: course ? subjectColor(course) : "" });
}
window.openTask = openTask;
