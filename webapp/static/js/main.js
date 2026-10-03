// Запуск — последним, когда все части уже загружены — часть WebApp (раньше всё жило в одном index.html на 1945 строк).
// Файлы подключаются по порядку и делят глобальную область видимости.

renderSdoTile(readSdoTile());     // плитка «Баллы СДО»: сразу последнее сохранённое,
loadToday().then(loadSdoTile).then(initPlanHome);    // а свежее — после главной, не задерживая её
                                  // (план автопилота — последним: решатель и СДО)
initHomeAdd();
initOptional();
renderChat();
loadChatSubjects();

(function () {
  const q = new URLSearchParams(location.search).get("file");
  const sp = (tg && tg.initDataUnsafe && tg.initDataUnsafe.start_param) || "";
  const id = parseInt(q || (sp.startsWith("file_") ? sp.slice(5) : ""), 10);
  if (id) openFileFromLink(id);
})();

// Кнопка из уведомления бота открывает приложение сразу на нужном экране:
// ?tab=deadlines / files / chat / sdo / search / notify / plan («Корнилов», keyboards.app_button).
(function () {
  const tab = new URLSearchParams(location.search).get("tab");
  const deepLink = tab || new URLSearchParams(location.search).get("file");
  if (!deepLink) maybeOnboard();      // из уведомления — сразу к делу, знакомство потом
  if (tab === "sdo") openSdo();
  else if (tab === "notify") openNotify();
  else if (tab === "plan") openPlan();
  else if (["deadlines", "files", "chat", "search"].includes(tab)) switchTab(tab);
})();

// Системная «Назад» Telegram и листы снизу: пока открыт лист (или меню
// «Ещё»), «Назад» закрывает его, а не уводит с экрана под ним. Свои
// обработчики экранов (папка, предмет СДО, расписание из поиска) на это
// время снимаются и потом возвращаются — Telegram вызывает все сразу.
(function () {
  if (!tg || !tg.BackButton) return;
  const NESTED = () => [closeFolder, sdoBack, closeTarget];
  let sheetBack = false;

  function closeTopSheet() {
    haptic();
    const more = document.getElementById("more-menu");
    if (more.classList.contains("open")) { toggleMore(false); return; }
    const open = document.querySelectorAll(".sheet-backdrop.open");
    if (open.length) open[open.length - 1].classList.remove("open");
  }

  function restoreBack() {
    const active = (document.querySelector(".view.active") || {}).id || "";
    if (["view-subject", "view-tk", "view-task"].includes(active)) { tg.BackButton.onClick(sdoBack); tg.BackButton.show(); }
    else if (active === "view-search" && document.getElementById("target-view").style.display === "block") {
      tg.BackButton.onClick(closeTarget); tg.BackButton.show();
    } else if (active === "view-files") syncFileBack();
    else tg.BackButton.hide();
  }

  function sync() {
    const anyOpen = !!document.querySelector(".sheet-backdrop.open, #more-menu.open");
    if (anyOpen && !sheetBack) {
      sheetBack = true;
      NESTED().forEach(fn => tg.BackButton.offClick(fn));
      tg.BackButton.onClick(closeTopSheet);
      tg.BackButton.show();
    } else if (!anyOpen && sheetBack) {
      sheetBack = false;
      tg.BackButton.offClick(closeTopSheet);
      restoreBack();
    }
  }

  const obs = new MutationObserver(sync);
  document.querySelectorAll(".sheet-backdrop, #more-menu").forEach(el => obs.observe(el, { attributes: true, attributeFilter: ["class"] }));
})();
