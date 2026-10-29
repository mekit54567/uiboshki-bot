/* «Было и стало» (/history): слева — бот из апреля 2026 в чате Telegram,
   справа — экран приложения сейчас. Тексты бота восстановлены из кода тех
   дней: first — коммит 53e40c0 (24.04, 00:19), akadem — c979db2 (25.04, 18:43).
   День — четверг 08.10.2026, как у демо-данных приложения справа. */
(function () {
  "use strict";

  var KB = {
    first: [["📅 Расписание сегодня", "📋 Дедлайны"], ["➕ Добавить дедлайн", "🤖 Решить задачу"], ["🔕 Отписаться", "🔔 Подписаться"]],
    akadem: [["📅 Сегодня", "📆 Неделя", "🌅 Завтра"], ["⏭ Следующая", "📋 Дедлайны", "🤖 Решить"],
             ["📁 Файлы", "📝 ДЗ", "🌤 Погода"], ["🏆 Рейтинг", "⚙️ Настройки", "⋯ Действия"]],
    stop: [["🛑 Завершить диалог"]],
    subjects: [["Математика", "Информатика"], ["Экономика", "Статистика"], ["Бизнес-анализ", "Другое"]]
  };

  // расписание дня — schedule_parser.format_schedule (первый коммит) и format_day (25.04);
  // название пары тогда шло как в календаре МИРЭА, с «ЛК»/«ПР» впереди
  var DAY = [
    ["09:00", "ЛК Моделирование бизнес-процессов", "А-17 (В-78)"],
    ["10:40", "ЛК Анализ и диагностика финансово-хозяйственной деятельности предприятия", "А-17 (В-78)"],
    ["12:40", "ПР Анализ и диагностика финансово-хозяйственной деятельности предприятия", "ИВЦ-117 (В-78)"],
    ["14:20", "ПР Архитектура предприятия", "А-223 (В-78)"],
    ["16:20", "ПР Анализ данных", "ИВЦ-126 (В-78)"]
  ];

  function dayFirst() {
    var s = "📅 <b>Четверг, 08.10.2026</b>\n";
    DAY.forEach(function (l, i) { s += "\n" + (i + 1) + ". ⏰ " + l[0] + "  <b>" + l[1] + "</b>\n   📍 " + l[2]; });
    return s;
  }

  function dayAkadem(name, date, lessons) {
    var head = "📅 <b>" + name + "</b>, " + date;
    if (!lessons.length) return head + "\n🎉 Пар нет!";
    return [head, ""].concat(lessons.map(function (l, i) {
      return "┌ <b>Пара " + (i + 1) + "</b>  ⏰ " + l[0] + "\n│ 📖 " + l[1] + "\n└ 📍 " + l[2];
    })).join("\n\n");
  }

  var WEEK = [
    ["Понедельник", "05.10.2026", [["09:00", "СР Производственная практика", "кафедра (В-78)"]]],
    ["Вторник", "06.10.2026", []],
    ["Среда", "07.10.2026", [["09:00", "СР Производственная практика", "кафедра (В-78)"]]]
  ];

  function weekAkadem() {
    var s = "📆 <b>Расписание на эту неделю</b>\n";
    WEEK.forEach(function (d) { s += "\n" + dayAkadem(d[0], d[1], d[2]) + "\n─────────────────"; });
    return s + "\n…";
  }

  // дедлайны — handlers/deadlines.format_deadlines; полоска — scheduler.progress_bar (25.04)
  var CHATS = {
    first: {
      today: [["me", "📅 Расписание сегодня"], ["bot", dayFirst()]],
      week: [["me", "📆 Неделя"],
             ["hint", "Кнопки «Неделя» ещё нет — она появилась в 01:10, в v2.0. Тогда бот просто молчал."]],
      deadlines: [["me", "📋 Дедлайны"], ["bot",
        "📋 <b>Дедлайны группы:</b>\n\n\n[3] <b>Лабораторная работа 3, ООАиП</b>\n   📅 2026-10-08 23:59 — 🔴 сегодня!" +
        "\n\n[4] <b>Курсовая: глава 1, Бизнес-анализ</b>\n   📅 2026-10-14 23:59 — 🟢 через 6 дн." +
        "\n\n\n/done ID — выполнено  |  /del ID — удалить"]],
      solver: [["me", "🤖 Решить задачу"],
               ["bot", "🤖 Пришли мне задачу:\n• Просто напиши текст задания\n• Или прикрепи <b>фото/скриншот</b>\n\nОтправь /cancel чтобы отменить."],
               ["me", "Найди среднее: 4, 8, 15, 16, 23, 42"], ["bot", "🧠 Решаю задачу, секунду..."],
               ["bot ex", "📌 **Краткое решение:** $\\bar{x} = \\frac{108}{6} = 18$\n\n🔍 **Шаг 1.** Складываем: $4 + 8 + 15 + 16 + 23 + 42 = 108$\n" +
                 "🔍 **Шаг 2.** Делим на количество: $\\frac{108}{6}$\n\n✅ **Ответ:** 18 🎉"]],
      menu: [["me", "/start"], ["bot",
        "👋 Привет, <b>Аня</b>!\n\nЯ бот группы МИРЭА «Бизнес-информатика» 🎓\n\nЧто умею:\n" +
        "📅 <b>Расписание</b> — пары на сегодня каждое утро в 7:30\n📋 <b>Дедлайны</b> — общий трекер для группы\n" +
        "🤖 <b>Решалка</b> — кидай фото или текст задачи\n\nИспользуй кнопки ниже или команды:"]]
    },
    akadem: {
      today: [["me", "📅 Сегодня"], ["bot", dayAkadem("Четверг", "08.10.2026", DAY)]],
      week: [["me", "📆 Неделя"], ["bot", weekAkadem()]],
      deadlines: [["me", "📋 Дедлайны"], ["bot",
        "📋 <b>Дедлайны группы</b>\n\n\n[3] <b>Лабораторная работа 3, ООАиП</b>\n   📅 08.10.2026 в 23:59 — 🔴 сегодня!\n   ━━━━━━━━━━ 100%" +
        "\n\n[4] <b>Курсовая: глава 1, Бизнес-анализ</b>\n   📅 14.10.2026 в 23:59 — 🟢 через 6 дн.\n   ━━━━━━╌╌╌╌ 60%" +
        "\n\n\n/done ID — выполнено  •  /del ID — удалить"]],
      solver: [["me", "🤖 Решить"], ["bot", "📚 Выбери предмет:"], ["me", "Статистика"],
               ["bot", "✅ Предмет: <b>Статистика</b>\n\nПришли задачу — текстом или фото 📸"],
               ["me", "Найди среднее: 4, 8, 15, 16, 23, 42"],
               ["bot ex", "📌 <b>1. Краткий ответ:</b> 18\n\n🧮 <b>2. Решение:</b>\n4 + 8 + 15 + 16 + 23 + 42 = 108\n108 ÷ 6 = 18\n\n✅ <b>3. Итог:</b> среднее — 18 🎉"],
               ["bot", "💬 Можешь уточнить или задать следующий вопрос.\nНажми <b>🛑 Завершить диалог</b> чтобы выйти."]],
      menu: [["me", "/start"], ["bot",
        "👋 Привет, <b>Аня</b>!\n\nЯ бот группы <b>УИБО-03-24</b> 🎓\n\n━━━━━━━━━━━━━━━━━━━\n📅 Расписание — сегодня, завтра, неделя\n" +
        "📋 Дедлайны — трекер группы\n🤖 Решалка — текст или фото задачи\n📁 Файлы — лекции и методички\n📝 ДЗ — доска домашних заданий\n" +
        "🌤 Погода — прямо сейчас\n⋯ Действия — всё остальное\n━━━━━━━━━━━━━━━━━━━"]]
    }
  };

  var SHOTS = {
    today: ["today", "Экран «Сегодня»: идёт пара, сколько до конца, где следующая"],
    week: ["week", "Экран «Неделя»: пары по дням"],
    deadlines: ["deadlines", "Экран «Сдать»: сроки из СДО и сколько осталось"],
    solver: ["assistant", "Kapi ИИ отвечает по лекциям группы со ссылками на слайды"],
    menu: ["more", "Экран «Ещё»: баллы БРС, ачивки, рейтинг, настройки"]
  };

  var state = { ver: "akadem", tab: "today" };
  var oldScreen = document.getElementById("old-screen");
  var shot = document.getElementById("new-shot");

  function kbFor() {
    if (state.tab === "solver") return state.ver === "akadem" ? KB.stop : KB[state.ver];
    return KB[state.ver];
  }

  function render() {
    var msgs = CHATS[state.ver][state.tab];
    var html = '<div class="tg"><div class="tg-top"><div class="tg-ava">У</div><div><b>УИБО-03-24</b><span>бот</span></div></div><div class="tg-chat">';
    msgs.forEach(function (m) {
      var kind = m[0];
      if (kind === "hint") { html += '<div class="tg-hint">' + m[1] + "</div>"; return; }
      var text = m[1];
      html += '<div class="msg ' + (kind === "me" ? "me" : "bot") + (kind === "bot ex" ? " ex" : "") + '">' + text +
        '<small>10:07</small></div>';
    });
    html += '</div><div class="kb">';
    kbFor().forEach(function (row) {
      html += '<div style="grid-template-columns:repeat(' + row.length + ',1fr)">' +
        row.map(function (b) { return "<span>" + b + "</span>"; }).join("") + "</div>";
    });
    oldScreen.innerHTML = html + "</div></div>";
    // листаем к последнему нажатию: видно вопрос и начало ответа (длинный ответ — дальше прокруткой)
    var chat = oldScreen.querySelector(".tg-chat");
    var mine = chat.querySelectorAll(".msg.me");
    var last = mine[mine.length - 1];
    chat.scrollTop = last ? last.offsetTop - 8 : chat.scrollHeight;
    var s = SHOTS[state.tab];
    shot.src = "/site/history/" + s[0] + ".jpg";
    shot.alt = s[1];
  }

  function pick(selector, attr, key) {
    document.querySelectorAll(selector).forEach(function (b) {
      b.addEventListener("click", function () {
        state[key] = b.getAttribute(attr);
        document.querySelectorAll(selector).forEach(function (x) {
          var on = x === b;
          x.classList.toggle("on", on);
          x.setAttribute("aria-selected", on ? "true" : "false");
        });
        render();
      });
    });
  }

  // на телефоне виден один экран: «Тогда» или «Сейчас»
  document.querySelectorAll(".view [data-view]").forEach(function (b) {
    b.addEventListener("click", function () {
      var stage = document.querySelector(".stage");
      var view = b.getAttribute("data-view");
      stage.classList.toggle("show-old", view === "old");
      stage.classList.toggle("show-new", view === "new");
      document.querySelectorAll(".view [data-view]").forEach(function (x) {
        x.setAttribute("aria-selected", x === b ? "true" : "false");
      });
    });
  });

  pick(".seg [data-ver]", "data-ver", "ver");
  pick(".chips [data-tab]", "data-tab", "tab");
  render();
})();
