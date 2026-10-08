// Файлы: папки предметов, типы, правка и удаление — часть WebApp (раньше всё жило в одном index.html на 1945 строк).
// Файлы подключаются по порядку и делят глобальную область видимости.

// ── Файлы ─────────────────────────────────────────────────────────────────

let fileSearchTimer = null;
document.getElementById("file-search").addEventListener("input", (e) => {
  clearTimeout(fileSearchTimer);
  fileSearchTimer = setTimeout(() => loadFiles(e.target.value), 300);
});

// Файлы: предметы-папки → внутри разделы по типам (лекции, практики, КР…).
// Поиск — плоский список с предметом и типом у каждого файла.
let fileItems = [];
let fileCategories = [];
let fileSubject = null;   // null — список папок; строка — открыт предмет ("" — без предмета)
let fileCat = "";
let fileQuery = "";
let folderList = [];
let fileIndex = {};
let fileCanDelete = false;   // удалять (у всей группы) может только староста

// Разделы приходят с сервера с эмодзи (бот показывает их в чате) — в WebApp
// вместо эмодзи своя иконка раздела (js/icons.js).
const CAT_ICONS = { lecture: "book", practice: "edit", control: "note", method: "bookOpen", exam: "cap", other: "folder" };

function catText(label) {
  return (label || "").replace(/^[^\p{L}\p{N}«"]+/u, "");
}

function catLabel(c) {
  return icon(CAT_ICONS[c.key] || "folder") + " " + escapeHtml(catText(c.label));
}

// Файл с текстом нажимается целиком (кроме кнопок) — открывается конспект.
// Пилюля у названия: «есть текст» — ИИ прочитал файл и сделает конспект,
// «конспект» — уже готов (дизайн-ревью, п. 14: крошечный значок не замечали).
function fileCard(f, withPlace) {
  const sub = withPlace ? (f.subject || "Без предмета") + " · " + catText(f.category_label) : (f.file_name || "");
  const badge = f.has_summary ? '<span class="fpill sum">' + icon("sparkle") + 'конспект</span>'
    : f.has_text ? '<span class="fpill txt">' + icon("bookOpen") + 'есть текст</span>' : '';
  return '<div class="file-card" id="fc-' + f.id + '">' +
    fileTypeIcon(f.file_name) +
    '<div class="fbody' + (f.has_text ? ' tap" onclick="openSummary(' + f.id + ')' : '') + '">' +
    '<div class="ft">' + escapeHtml(f.title) + (badge ? '\u2060' + badge : '') + '</div>' +
    '<div class="fs">' + escapeHtml(sub) + '</div></div>' +
    '<button class="dl" onclick="downloadFile(' + f.id + ', this)" aria-label="Скачать">' + icon("download") + '</button>' +
    '<button onclick="openFile(' + f.id + ', this)">В чат</button>' +
    (f.can_edit ? '<button class="edit" onclick="openFileSheet(' + f.id + ')" aria-label="Изменить">' + icon("edit") + '</button>' : '') +
  '</div>';
}

// «Практика 2» раньше «Практики 10», серии с одинаковым началом — рядом.
const titleCollator = new Intl.Collator("ru", { numeric: true, sensitivity: "base" });

function countByCat(files) {
  const counts = {};
  files.forEach(f => counts[f.category] = (counts[f.category] || 0) + 1);
  return counts;
}

function renderFolders(list) {
  const bySubject = {};
  fileItems.forEach(f => (bySubject[f.subject] = bySubject[f.subject] || []).push(f));
  folderList = Object.keys(bySubject).sort((a, b) => a === "" ? 1 : b === "" ? -1 : a.localeCompare(b, "ru"));
  list.innerHTML = folderList.map((s, i) => {
    const files = bySubject[s];
    const counts = countByCat(files);
    const parts = fileCategories.filter(c => counts[c.key]).map(c => icon(CAT_ICONS[c.key] || "folder", "inl") + counts[c.key]);
    return '<div class="folder-card" onclick="openFolder(' + i + ')">' +
      '<span class="ic">' + icon("folder") + '</span>' +
      '<div style="min-width:0"><div class="ft">' + escapeHtml(s || "Без предмета") + '</div>' +
      '<div class="fs">' + files.length + " " + plural(files.length, "файл", "файла", "файлов") +
        (parts.length > 1 ? " · " + parts.join(" · ") : "") + '</div></div>' +
      '<span class="go">›</span></div>';
  }).join("");
}

function renderFiles() {
  const head = document.getElementById("file-head");
  const list = document.getElementById("file-list");
  head.innerHTML = "";
  if (fileQuery) {
    list.innerHTML = (fileItems.length ? fileItems.map(f => fileCard(f, true)).join("") : "") + '<div id="lec-hits"></div>';
    syncFileBack();
    return;
  }
  const subjects = [...new Set(fileItems.map(f => f.subject))];
  const single = subjects.length === 1;
  if (fileSubject === null && !single) { renderFolders(list); syncFileBack(); return; }
  const subject = single ? subjects[0] : fileSubject;
  const files = fileItems.filter(f => f.subject === subject);
  const counts = countByCat(files);
  const cats = fileCategories.filter(c => counts[c.key]);
  if (fileCat && !counts[fileCat]) fileCat = "";

  head.innerHTML = (single ? "" : '<button class="file-back" onclick="closeFolder()">‹ Все предметы</button>') +
    '<div class="file-subj-title">' + escapeHtml(subject || "Без предмета") + '</div>' +
    (cats.length > 1 ? '<div class="chips-row" id="file-cats"></div>' : "");
  if (cats.length > 1) {
    const box = document.getElementById("file-cats");
    [{ key: "", label: "Все" }, ...cats].forEach(c => {
      const b = document.createElement("button");
      b.innerHTML = (c.key ? catLabel(c) : "Все") + " · " + (c.key ? counts[c.key] : files.length);
      b.classList.toggle("active", c.key === fileCat);
      b.onclick = () => { fileCat = c.key; haptic(); renderFiles(); };
      box.appendChild(b);
    });
  }
  // Удалить разом папку или раздел (лишнее из выгрузки СДО) — у всей
  // группы, поэтому только старосте.
  const inView = fileCat ? files.filter(f => f.category === fileCat) : files;
  if (fileCanDelete && inView.length) {
    const what = fileCat ? "раздел «" + catText((cats.find(c => c.key === fileCat) || {}).label) + "»" : "папку «" + (subject || "Без предмета") + "»";
    head.insertAdjacentHTML("beforeend", '<button class="file-del inline" id="file-del-all">' + icon("trash") + ' Удалить ' + escapeHtml(what) +
      " (" + inView.length + ")</button>");
    document.getElementById("file-del-all").onclick = () => deleteFiles(inView.map(f => f.id), what);
  }
  const shown = fileCat ? cats.filter(c => c.key === fileCat) : cats;
  list.innerHTML = shown.map(c =>
    '<div class="group-title">' + catLabel(c) + ' · ' + counts[c.key] + '</div>' +
    files.filter(f => f.category === c.key).sort((a, b) => titleCollator.compare(a.title, b.title))
      .map(f => fileCard(f, false)).join("")
  ).join("");
  syncFileBack();
}

function openFolder(i) {
  fileSubject = folderList[i];
  fileCat = "";
  haptic();
  renderFiles();
  window.scrollTo(0, 0);
}

function closeFolder() {
  fileSubject = null;
  fileCat = "";
  renderFiles();
}

// Системная «Назад» Telegram внутри папки возвращает к списку предметов.
function syncFileBack() {
  if (!tg || !tg.BackButton) return;
  tg.BackButton.offClick(closeFolder);
  const inFolder = fileSubject !== null && !fileQuery && new Set(fileItems.map(f => f.subject)).size > 1;
  if (inFolder) { tg.BackButton.onClick(closeFolder); tg.BackButton.show(); }
  else tg.BackButton.hide();
}

async function loadFiles(q) {
  const list = document.getElementById("file-list");
  if (q !== undefined) fileQuery = q.trim();
  try {
    const data = await api("/api/files?q=" + encodeURIComponent(fileQuery));
    fileItems = data.items;
    fileCategories = data.categories || [];
    fileCanDelete = !!data.can_delete;
    fileIndex = {};
    fileItems.forEach(f => fileIndex[f.id] = f);
    if (fileSubject !== null && !fileItems.some(f => f.subject === fileSubject)) fileSubject = null;
    if (!fileItems.length) {
      list.innerHTML = fileQuery ? '<div id="lec-hits"></div>'
        : capyEmpty("Файлов пока нет", "Загрузи их в боте: /upload");
      document.getElementById("file-head").innerHTML = "";
      syncFileBack();
      if (fileQuery) loadLectureHits(fileQuery, true);
      return;
    }
    renderFiles();
    if (fileQuery) loadLectureHits(fileQuery, false);
  } catch (e) {
    list.innerHTML = capyError(e.message);
  }
}

// ── Поиск внутри лекций ──────────────────────────────────────────────────
// Под файлами по названию — места в самих лекциях: «где было про NPV?» →
// «Лекция 5 · слайд 12» и отрывок; нажал — открылась страница (openPage).
let lecSeq = 0;

async function loadLectureHits(q, alone) {
  const my = ++lecSeq;
  const box = document.getElementById("lec-hits");
  if (!box) return;
  if (q.length < 3) { if (alone) box.innerHTML = capyEmpty("Ничего не нашлось", null, "sad"); return; }
  box.innerHTML = '<div class="lec-head">В тексте лекций</div><div class="skel" style="height:64px"></div>';
  let d;
  try {
    d = await api("/api/lecture-search?q=" + encodeURIComponent(q));
  } catch (e) {
    if (my === lecSeq) box.innerHTML = alone ? capyEmpty("Ничего не нашлось", null, "sad") : "";
    return;
  }
  if (my !== lecSeq || fileQuery !== q) return;      // уже ищем другое
  if (!d.items.length) {
    box.innerHTML = alone ? capyEmpty("Ничего не нашлось",
      d.ready ? "Ни в названиях, ни в тексте лекций" : "Тексты лекций ещё индексируются", "sad") : "";
    return;
  }
  const stems = q.toLowerCase().split(/[^\wа-яё]+/i).filter(w => w.length >= 3).map(w => w.slice(0, 5));
  box.innerHTML = '<div class="lec-head">В тексте лекций</div>' + d.items.map(h =>
    '<div class="lec-hit" onclick="openPage(' + h.file_id + ',' + h.page + ')">' +
      '<div class="lh-t">' + icon("bookOpen", "inl") + ' ' + escapeHtml(h.title) + ' · <span>' + escapeHtml(h.place) + '</span></div>' +
      '<div class="lh-s">' + markStems(escapeHtml(h.snippet), stems) + '</div>' +
      (h.subject ? '<div class="lh-subj">' + escapeHtml(h.subject) + '</div>' : '') +
    '</div>').join("");
}

// подсветка слов запроса в уже экранированном отрывке
function markStems(html, stems) {
  if (!stems.length) return html;
  const re = new RegExp("(" + stems.map(s => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") + ")[\\wа-яё]*", "gi");
  return html.replace(re, (m, g, off) => html[off - 1] === "&" ? m : "<mark>" + m + "</mark>");   // не внутри &quot;
}

let fileEditing = null;
let fileEditCat = "";

function openFileSheet(id) {
  const f = fileIndex[id];
  if (!f) return;
  haptic();
  fileEditing = f;
  fileEditCat = f.category;
  document.getElementById("fe-title").value = f.title;
  document.getElementById("fe-subject").value = f.subject;
  const subjects = [...new Set(fileItems.map(x => x.subject).filter(Boolean))].sort();
  document.getElementById("fe-subjects").innerHTML = subjects.map(s => '<option value="' + escapeHtml(s) + '">').join("");
  renderFileEditCats();
  document.getElementById("fe-delete").style.display = fileCanDelete ? "block" : "none";
  document.getElementById("file-sheet").classList.add("open");
}

function renderFileEditCats() {
  const box = document.getElementById("fe-cats");
  box.innerHTML = "";
  fileCategories.forEach(c => {
    const b = document.createElement("button");
    b.innerHTML = catLabel(c);
    b.classList.toggle("active", c.key === fileEditCat);
    b.onclick = () => { fileEditCat = c.key; haptic(); renderFileEditCats(); };
    box.appendChild(b);
  });
}

async function deleteFiles(ids, what) {
  const n = ids.length;
  const text = n === 1 ? "Удалить " + what + "? Текст для ИИ тоже удалится."
    : "Удалить " + what + " — " + n + " " + plural(n, "файл", "файла", "файлов") + "? Из СДО их потом заново не подтянет.";
  if (!(await confirmDialog(text))) return;
  try {
    const res = await api("/api/files/delete", { method: "POST", body: JSON.stringify({ ids: ids }) });
    haptic("success");
    showToast("🗑 Удалено: " + res.deleted);
    closeFileSheet();
    if (n > 1) fileCat = "";
    loadFiles();
  } catch (e) {
    alert("Не получилось: " + e.message);
  }
}

function closeFileSheet() {
  document.getElementById("file-sheet").classList.remove("open");
}

async function submitFileEdit() {
  const title = document.getElementById("fe-title").value.trim();
  if (!title) { document.getElementById("fe-title").focus(); return; }
  const btn = document.getElementById("fe-submit");
  btn.disabled = true;
  try {
    await api("/api/files/" + fileEditing.id, { method: "PATCH", body: JSON.stringify({
      title: title,
      subject: document.getElementById("fe-subject").value.trim(),
      category: fileEditCat,
    }) });
    haptic("success");
    showToast("✓ Сохранено");
    closeFileSheet();
    loadFiles();
  } catch (e) {
    alert("Не получилось: " + e.message);
  } finally {
    btn.disabled = false;
  }
}

function openFile(id, btn) {
  sendToChat("/api/files/" + id + "/send", "file_" + id, btn);
}

// «📥 Скачать»: системное окно Telegram «Скачать файл?» → на iPhone меню
// «Сохранить в Файлы / Поделиться», на Android — в Загрузки. Без сворачивания
// WebApp и пересылки из чата. Старый Telegram (до 8.0) или файл больше 20 МБ —
// шлём в чат, как «В чат».
async function downloadFile(id, btn) {
  if (!(tg && tg.downloadFile && tg.isVersionAtLeast && tg.isVersionAtLeast("8.0"))) {
    showToast("Telegram старый для скачивания — отправляю в чат");
    return openFile(id, btn);
  }
  btn.disabled = true; btn.classList.add("sending");
  let link = null;
  try {
    link = await api("/api/files/" + id + "/link", { method: "POST" });
  } catch (e) {
    btn.disabled = false; btn.classList.remove("sending");
    showToast("Файл большой для скачивания — отправляю в чат");
    return openFile(id, btn);
  }
  btn.disabled = false; btn.classList.remove("sending");
  try {
    tg.downloadFile({ url: link.url, file_name: link.file_name }, ok => { if (ok) haptic("success"); });
  } catch (e) {
    openFile(id, btn);
  }
}

// Ссылка из бота «Открыть в WebApp» (?file=<id>): сразу папка предмета и
// подсвеченный файл.
async function openFileFromLink(id) {
  // поиск по файлам сбрасываем: иначе ищем среди найденного и «Файл не найден»
  clearTimeout(fileSearchTimer);
  fileQuery = "";
  document.getElementById("file-search").value = "";
  switchTab("files");
  await loadFiles();
  const f = fileIndex[id];
  if (!f) { showToast("Файл не найден — возможно, его удалили"); return; }
  fileSubject = f.subject; fileCat = "";
  renderFiles();
  const card = document.getElementById("fc-" + id);
  if (card) {
    card.scrollIntoView({ block: "center" });
    card.classList.add("hl");
    setTimeout(() => card.classList.remove("hl"), 2500);
  }
}

// ── Конспект лекции ───────────────────────────────────────────────────────
// Один на файл и общий для всех: пока никто не нажал «Сделать конспект», его
// нет; сделал один — открывается у всех сразу (lecture_summary.py).

let sumFile = null;
let sumData = null;

async function openSummary(id) {
  haptic();
  sumFile = id;
  sumData = null;
  const box = document.getElementById("sum-content");
  box.innerHTML = '<div class="skel" style="height:22px;width:60%"></div><div class="skel" style="height:120px;margin-top:14px"></div>';
  document.getElementById("sum-sheet").classList.add("open");
  try {
    const d = await api("/api/summary/" + id);
    if (sumFile === id) { sumData = d; renderSummary(false); }
  } catch (e) {
    box.innerHTML = capyError(e.message);
  }
}

function renderSummary(busy) {
  const d = sumData;
  const box = document.getElementById("sum-content");
  const head = '<h3>' + escapeHtml(d.title) + '</h3><p class="sheet-hint">' +
    escapeHtml((d.subject || "Без предмета") + " · " + catText(d.category_label)) + '</p>';
  if (d.summary) {
    const when = d.created_at ? " · " + new Date(d.created_at).toLocaleDateString("ru", { day: "numeric", month: "long" }) : "";
    box.innerHTML = head + '<div class="sum-body">' + d.summary + '</div>' +
      '<p class="sheet-hint sum-foot">' + icon("sparkle", "inl") + ' Конспект от ИИ' + when +
      '. Может ошибаться — главное сверяй с лекцией.</p>';
    return;
  }
  box.innerHTML = head +
    '<div class="sum-empty"><span class="sum-ic">' + icon("sparkle") + '</span>' +
    '<b>Конспекта пока нет</b>' +
    '<p>ИИ прочитает лекцию и коротко перескажет главное. Сделаешь один раз — конспект увидят все.</p></div>' +
    '<button class="primary" id="sum-make" onclick="makeSummary()"' + (busy ? ' disabled' : '') + '>' +
    (busy ? 'Читаю лекцию…' : 'Сделать конспект') + '</button>' +
    (busy ? '<p class="sheet-hint sum-wait">Обычно до минуты. Можно закрыть — конспект сохранится.</p>' : '');
}

async function makeSummary() {
  const id = sumFile;
  if (!sumData || sumData.summary) return;
  haptic();
  renderSummary(true);
  try {
    const d = await api("/api/summary/" + id, { method: "POST" });
    const f = fileIndex[id];
    if (f) {
      f.has_summary = true;
      const card = document.getElementById("fc-" + id);
      if (card) card.outerHTML = fileCard(f, !!fileQuery);
    }
    if (sumFile !== id) { showToast("Конспект готов: " + d.title); return; }
    haptic("success");
    sumData = d;
    renderSummary(false);
  } catch (e) {
    if (sumFile === id) renderSummary(false);
    showToast(e.message);
  }
}

