// ── 152-ФЗ: согласие, тексты и «удалить все мои данные» (privacy.py) ────────
// Галочка по умолчанию не стоит, кнопка рядом неактивна, пока её нет. Тексты
// согласия и политики — /api/legal/<имя> (legal_texts.py): рисуем их сами, в
// дизайне приложения, листом поверх открытого — введённое в поле не теряется.

function consentRow(id, onchange, extra) {
  return '<label class="consent-row"><input type="checkbox" id="' + id + '" onchange="' + onchange + '">' +
    '<span class="consent-box">' + icon("check") + '</span>' +
    '<span>Даю <a class="legal-link" onclick="openLegal(event, \'consent\')">согласие на обработку персональных данных</a>' +
    (extra || "") + '</span></label>' +
    '<p class="consent-more">Подробнее — в <a class="legal-link" onclick="openLegal(event, \'privacy\')">' +
    'Политике обработки персональных данных</a></p>';
}

function consentChecked(id) {
  const box = document.getElementById(id);
  return !!(box && box.checked);
}

async function openLegal(ev, name) {
  if (ev) { ev.preventDefault(); ev.stopPropagation(); }   // ссылка в подписи галочки — не ставить её
  haptic();
  const box = document.getElementById("legal-body");
  document.getElementById("legal-sheet").classList.add("open");
  box.innerHTML = '<div class="skel" style="height:320px"></div>';
  let d;
  try { d = await api("/api/legal/" + name); } catch (e) {
    box.innerHTML = '<p class="hint">Не удалось загрузить текст: ' + escapeHtml(e.message) + '</p>';
    return;
  }
  box.innerHTML = '<h3>' + escapeHtml(d.title) + '</h3>' +
    '<p class="sheet-hint">Версия ' + escapeHtml(d.version) + ' от ' + escapeHtml(d.date) + '</p>' +
    '<div class="legal-text"><p class="legal-lead">' + escapeHtml(d.lead) + '</p>' +
    d.sections.map(s => '<h4>' + escapeHtml(s.title) + '</h4>' + s.blocks.map(b => b.ul
      ? '<ul>' + b.ul.map(i => '<li>' + escapeHtml(i) + '</li>').join("") + '</ul>'
      : '<p>' + escapeHtml(b.p) + '</p>').join("")).join("") + '</div>' +
    '<button class="primary" onclick="closeSheet(\'legal-sheet\')">Понятно</button>';
}

// Первый вход (и новая версия текста): /api/me → consent_needed. Новый
// человек (consent_blocked) до согласия видит только этот лист: API закрыт
// (403), лист не закрывается мимо — согласие или отказ с удалением данных;
// после «Продолжить» — заново, с данными. Кто был до согласий — один раз
// (/api/consent/asked), можно «Не сейчас» (Никита, 11.10).
let CONSENT_BLOCKED = false;

function maybeConsent(me) {
  if (me && me.erasing) return showErasing(me.erasing.text, false);
  if (!me || !me.consent_needed) return;
  CONSENT_BLOCKED = !!me.consent_blocked;
  document.getElementById("consent-body").innerHTML =
    '<div class="sec-hero"><span class="sec-shield">' + icon("shield") + '</span><div><h3>Твои данные</h3>' +
      '<p>Один раз — и пользуйся</p></div></div>' +
    '<p class="sheet-hint">Чтобы показывать расписание, дедлайны и баллы, приложению нужно хранить твой id, ' +
      'группу и настройки. Что именно и сколько — в политике, удалить всё можно в любой момент: ' +
      '«Ещё → Безопасность».</p>' +
    consentRow("pd-agree", "syncConsentBtn()") +
    '<button class="primary" id="pd-go" disabled onclick="giveConsent()">Продолжить</button>' +
    (CONSENT_BLOCKED ? '<button class="ghost" onclick="refuseConsent()">Не даю согласие</button>'
                     : '<button class="ghost" onclick="closeSheet(\'consent-sheet\')">Не сейчас</button>');
  document.getElementById("consent-sheet").classList.add("open");
  if (!CONSENT_BLOCKED) api("/api/consent/asked", { method: "POST", body: "{}" }).catch(() => {});
}

function syncConsentBtn() {
  document.getElementById("pd-go").disabled = !consentChecked("pd-agree");
}

async function giveConsent() {
  if (!consentChecked("pd-agree")) return;
  const btn = document.getElementById("pd-go");
  btn.disabled = true;
  try { await api("/api/consent", { method: "POST", body: JSON.stringify({ kind: "pd" }) }); } catch (e) {
    btn.disabled = false;
    showToast("⚠️ " + e.message);
    return;
  }
  haptic("success");
  closeSheet("consent-sheet");
  if (CONSENT_BLOCKED) location.reload();
}

async function refuseConsent() {
  if (!(await confirmDialog("Без согласия приложение не может хранить твои данные. Удалить то, что уже есть, и выйти?"))) return;
  await deleteMyData(true);
}

// «Удалить все мои данные» (ст. 21, Никита 18.10): фразой руками; сразу —
// выход везде и из СДО, полностью — через 7 дней (до этого можно попросить
// вернуть). Отказ от согласия до первого входа (confirmed) — сразу насовсем.
const ERASE_PHRASE = "удалить мои данные";

function erasePhraseOk(text) {
  const t = (text || "").toLowerCase().replace(/ё/g, "е").split(/\s+/).filter(Boolean).join(" ")
    .replace(/^[\s.!«»"']+|[\s.!«»"']+$/g, "");
  return t === ERASE_PHRASE;
}

function deleteMyData(confirmed) {
  if (confirmed) return eraseNow();
  haptic();
  document.getElementById("consent-body").innerHTML =
    '<div class="sec-hero"><span class="sec-shield">' + icon("trash") + '</span><div><h3>Удалить все твои данные?</h3>' +
      '<p>Профиль, группу, вход в СДО, историю баллов и посещений, личные дедлайны, устройства</p></div></div>' +
    '<p class="sheet-hint">Сразу — выход со всех устройств и из СДО, рассылки и ИИ остановятся. Полностью всё ' +
      'сотрём через 7 дней: если удалил по ошибке, до этого можно написать Никите (@Partykq) — вернём вручную, ' +
      'если получится, без гарантии.</p>' +
    '<p class="sheet-hint">Чтобы удалить, впиши: <b>' + ERASE_PHRASE + '</b></p>' +
    '<input class="searchbox" id="erase-phrase" autocomplete="off" autocapitalize="off" spellcheck="false" ' +
      'placeholder="' + ERASE_PHRASE + '" oninput="document.getElementById(\'erase-go\').disabled = !erasePhraseOk(this.value)">' +
    '<button class="primary danger" id="erase-go" disabled onclick="eraseByPhrase()">Удалить</button>' +
    '<button class="ghost" onclick="closeSheet(\'consent-sheet\')">Оставить</button>';
  document.getElementById("consent-sheet").classList.add("open");
}

async function eraseByPhrase() {
  const phrase = document.getElementById("erase-phrase").value;
  if (!erasePhraseOk(phrase)) return;
  document.getElementById("erase-go").disabled = true;
  let r;
  try { r = await api("/api/me/delete", { method: "POST", body: JSON.stringify({ phrase }) }); } catch (e) {
    document.getElementById("erase-go").disabled = false;
    showToast("⚠️ " + e.message);
    return;
  }
  haptic("success");
  showErasing(r.text, true);
}

async function eraseNow() {
  try { await api("/api/me/delete", { method: "POST", body: JSON.stringify({ confirm: true }) }); } catch (e) {
    showToast("⚠️ " + e.message);
    return;
  }
  haptic("success");
  showErasing("", true);
}

// Данные удаляются (или уже удалены): лист мимо не закрывается. leave — сразу
// после удаления: закрыть Mini App или выйти из PWA.
function showErasing(text, leave) {
  ERASED = true;
  document.querySelectorAll(".sheet-backdrop.open").forEach(s => s.classList.remove("open"));
  document.getElementById("consent-body").innerHTML =
    '<div class="sec-hero"><span class="sec-shield">' + icon("check") + '</span><div><h3>' +
      (text ? "Данные удаляются" : "Данные удалены") + '</h3><p>' +
      (text ? "Вход на всех устройствах и в СДО уже удалён" : "Всё о тебе стёрто") + '</p></div></div>' +
    '<p class="sheet-hint">' + escapeHtml(text || "Если вернёшься — начнём с нуля.") + '</p>';
  document.getElementById("consent-sheet").classList.add("open");
  if (!leave) return;
  if (IN_TG) { setTimeout(() => { try { tg.close(); } catch (e) {} }, 4000); return; }
  saveToken("");
  try { navigator.serviceWorker.controller.postMessage("logout"); } catch (e) {}
  setTimeout(() => location.replace("/app"), 4000);
}
