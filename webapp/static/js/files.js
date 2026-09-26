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

function fileIcon(name) {
  const n = (name || "").toLowerCase();
  if (n.endsWith(".pdf")) return "📕";
  if (n.endsWith(".docx") || n.endsWith(".doc")) return "📘";
  if (n.endsWith(".pptx") || n.endsWith(".ppt")) return "📙";
  if (/\.(jpg|jpeg|png|webp)$/.test(n)) return "🖼";
  if (/\.(xlsx|xls|csv)$/.test(n)) return "📗";
  return "📄";
}

function fileCard(f, withPlace) {
  const sub = withPlace ? (f.subject || "Без предмета") + " · " + f.category_label : (f.file_name || "");
  return '<div class="file-card">' +
    '<span class="ic">' + fileIcon(f.file_name) + '</span>' +
    '<div style="min-width:0"><div class="ft">' + escapeHtml(f.title) + (f.has_text ? '\u2060<span class="badge">📖</span>' : '') + '</div>' +
    '<div class="fs">' + escapeHtml(sub) + '</div></div>' +
    '<button onclick="openFile(' + f.id + ')">Открыть</button>' +
    (f.can_edit ? '<button class="edit" onclick="openFileSheet(' + f.id + ')" aria-label="Изменить">✏️</button>' : '') +
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
    const parts = fileCategories.filter(c => counts[c.key]).map(c => c.label.split(" ")[0] + " " + counts[c.key]);
    return '<div class="folder-card" onclick="openFolder(' + i + ')">' +
      '<span class="ic">📁</span>' +
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
    list.innerHTML = fileItems.length ? fileItems.map(f => fileCard(f, true)).join("") : '<div class="empty">Ничего не нашлось</div>';
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
      b.textContent = c.label + " · " + (c.key ? counts[c.key] : files.length);
      b.classList.toggle("active", c.key === fileCat);
      b.onclick = () => { fileCat = c.key; haptic(); renderFiles(); };
      box.appendChild(b);
    });
  }
  // Удалить разом папку или раздел (лишнее из выгрузки СДО) — у всей
  // группы, поэтому только старосте.
  const inView = fileCat ? files.filter(f => f.category === fileCat) : files;
  if (fileCanDelete && inView.length) {
    const what = fileCat ? "раздел «" + (cats.find(c => c.key === fileCat) || {}).label + "»" : "папку «" + (subject || "Без предмета") + "»";
    head.insertAdjacentHTML("beforeend", '<button class="file-del inline" id="file-del-all">🗑 Удалить ' + escapeHtml(what) +
      " (" + inView.length + ")</button>");
    document.getElementById("file-del-all").onclick = () => deleteFiles(inView.map(f => f.id), what);
  }
  const shown = fileCat ? cats.filter(c => c.key === fileCat) : cats;
  list.innerHTML = shown.map(c =>
    '<div class="group-title">' + escapeHtml(c.label) + ' · ' + counts[c.key] + '</div>' +
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
      list.innerHTML = '<div class="empty">' + (fileQuery ? "Ничего не нашлось" : "Файлов пока нет — загрузи их в боте: /upload") + '</div>';
      document.getElementById("file-head").innerHTML = "";
      syncFileBack();
      return;
    }
    renderFiles();
  } catch (e) {
    list.innerHTML = '<div class="empty">Не загрузилось: ' + escapeHtml(e.message) + '</div>';
  }
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
    b.textContent = c.label;
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

function openFile(id) {
  const link = "https://t.me/" + BOT_USERNAME + "?start=file_" + id;
  if (tg && tg.openTelegramLink) tg.openTelegramLink(link);
  else window.open(link, "_blank");
}
