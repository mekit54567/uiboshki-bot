// Полный прогон «как студент»: все вкладки и сценарии, проверки и скрины.
// Ответы API — запись стенда сайта (webapp/static/site/demo.json), время
// приложения зафиксировано на четверг 08.10.2026 10:07 (идёт первая пара).
// Запуск (из app/):
//   flutter build web --dart-define=API= --dart-define=NOW=2026-10-08T10:07:00+03:00
//   cd robot && npm install && node robot.js
// Итог — out/results.txt и скрины out/shots/robot-*.png (в CI — файлом
// у запуска, Actions → Artifacts). Есть FAIL — код выхода 1, проверка красная.
const fs = require('fs');
const path = require('path');
const L = require('./lib');

const results = [];
let cur = null;
function check(ok, what) {
  results.push(`${ok ? 'OK  ' : 'FAIL'} ${cur} — ${what}`);
  if (!ok) console.log('FAIL', cur, what);
}
// подпись недели: вне своей недели она кнопка («Сегодня»), и первым узлом может стать не она
const label0 = async (p) => (await L.nodes(p)).map((x) => x.label.split('\n')[0]).find((l) => /^\d+ неделя/.test(l)) || '';
const asked = (s, re) => s.log.asked.some((a) => re.test(a));

async function scenario(name, opts, fn) {
  cur = name;
  const s = await L.open(opts);
  try {
    await fn(s, s.page);
  } catch (e) {
    check(false, 'упал сценарий: ' + String(e.message || e).slice(0, 200));
    await L.shot(s.page, 'robot-crash-' + name.replace(/\W+/g, '_')).catch(() => {});
  }
  if (s.log.errors.filter((e) => !/Failed to load resource/.test(e)).length) check(false, 'ошибки в консоли: ' + s.log.errors.join(' | ').slice(0, 300));
  if (s.log.unknown.size) results.push(`note ${name} — ответов нет в записи стенда: ${[...s.log.unknown].join(', ')}`);
  await s.close();
}

(async () => {
  await scenario('Сегодня', {}, async (s, p) => {
    check(await L.has(p, 'Идёт первая пара'), 'заголовок «Идёт первая пара»');
    check(await L.has(p, 'до конца 23 мин'), 'до конца пары 23 мин (10:07 → 10:30)');
    check(await L.has(p, 'сегодня · 5 пар'), 'список из 5 пар');
    await L.shot(p, 'robot-today');
    await L.tap(p, /^10:40/, { wait: 1500 });
    check(await L.has(p, 'Бурлаков В. В.'), 'карточка пары открывается');
    await L.back(p);
    check(await L.has(p, 'сегодня · 5 пар'), 'назад — снова «Сегодня»');
  });

  await scenario('Неделя', {}, async (s, p) => {
    await L.tap(p, 'Неделя', { wait: 2000 });
    check((await label0(p)).startsWith('6 неделя'), 'открыта текущая неделя');
    await L.swipe(p, { from: [0.85, 0.6], to: [0.1, 0.6] });
    check((await label0(p)).startsWith('7 неделя'), 'свайп влево по ленте — следующая неделя');
    await L.swipe(p, { from: [0.1, 0.6], to: [0.85, 0.6] });
    check((await label0(p)).startsWith('6 неделя'), 'свайп вправо — назад');
    await L.tap(p, /^Прошлая неделя/, { wait: 1500 });
    check((await label0(p)).startsWith('5 неделя'), 'стрелка «назад»');
    await L.tap(p, /^Следующая неделя/, { wait: 1500 });
    await L.tap(p, /^По дням/, { wait: 1500 });
    check(await L.has(p, /, 5 пар$/), 'вид «По дням»: полоса дней с числом пар');
    await L.swipe(p, { from: [0.85, 0.6], to: [0.1, 0.6] });
    check((await label0(p)).startsWith('7 неделя'), 'свайп в виде «По дням»');
    await L.shot(p, 'robot-week-away');
    await L.tap(p, 'К сегодня', { wait: 1500 });
    check((await label0(p)).startsWith('6 неделя') && !(await L.has(p, 'К сегодня')), '«Сегодня» — обратно на свою неделю');
    await p.reload(); await p.waitForTimeout(3000); await p.evaluate(() => document.querySelector('flt-semantics-placeholder')?.click()); await p.waitForTimeout(600);
    await L.tap(p, 'Неделя', { wait: 2000 });
    check(await L.has(p, /, 5 пар$/), 'вид «По дням» запомнился после перезапуска');
    await L.shot(p, 'robot-week-days');
  });

  await scenario('Поиск расписания', {}, async (s, p) => {
    await L.tap(p, 'Неделя', { wait: 1500 });
    await L.tap(p, 'Поиск расписания', { wait: 1500 });
    await L.type(p, 195, 144, 'Сиганьков');
    check(await L.has(p, 'Сиганьков А. А.'), 'поиск находит преподавателя');
    await L.tap(p, /^Сиганьков/, { wait: 2000 });
    check(await L.has(p, 'Моделирование бизнес-процессов'), 'расписание преподавателя открылось');
    await L.shot(p, 'robot-teacher');
  });

  await scenario('Сдать', {}, async (s, p) => {
    await L.tap(p, 'Сдать', { wait: 1500 });
    check(await L.has(p, 'Впереди · 2') && await L.has(p, 'Сдано · 1'), 'счётчики «Впереди · 2», «Сдано · 1»');
    check(await L.has(p, 'горит · до 23:59'), 'горящий срок сверху');
    await L.swipe(p, { from: [0.1, 0.52], to: [0.9, 0.52] });
    check(asked(s, /POST \/api\/deadlines\/\d+\/toggle/), 'свайп вправо по сроку отмечает «сдано»');
    await L.tap(p, 'Свой срок', { wait: 1500 });
    check(await L.has(p, 'Новый срок'), 'лист «Новый срок»');
    await L.back(p);
    await L.tap(p, /^ДЗ группы/, { wait: 1500 });
    check(await L.has(p, 'ДЗ группы'), 'ДЗ группы открывается');
    await L.back(p);
    await L.tap(p, /^Сдано/, { wait: 1200 });
    check(await L.has(p, 'Эссе'), 'вкладка «Сдано»');
  });

  const ov = {};
  for (const m of ['3', '4', '5']) ov[`POST /api/sdo/goal/18673|${m}`] = { ...L.demo[`POST /api/sdo/goal/18673|${m}`], exam_left: 40, best: 134 };
  await scenario('Учёба и цель', { overrides: ov }, async (s, p) => {
    await L.tap(p, 'Учёба', { wait: 1500 });
    check((await L.nodes(p)).filter((n) => /^\d+\n/.test(n.label)).length >= 5, 'список предметов с баллами');
    await L.tap(p, /Объектно-ориентированный/, { wait: 2000 });
    check(await L.has(p, 'ещё 12 до «4»'), 'экран предмета: сколько до следующей отметки');
    await L.tap(p, 'Цель 5', { wait: 1500 });
    check(s.log.bodies.some(([k]) => k === 'POST /api/sdo/goal/18673|5'), 'выбор цели «5» уходит на сервер');
    check(await L.has(p, 'экзамен: до +40'), 'в цели учтён экзамен');
    await L.shot(p, 'robot-goal');
    await L.scroll(p, 350);
    await L.tap(p, /^Практическое задание 2/, { wait: 2000 });
    check(await L.has(p, 'Срок сдачи'), 'экран задания открывается');
  });

  await scenario('Файлы', {}, async (s, p) => {
    await L.tap(p, 'Учёба', { wait: 1500 });
    await L.tap(p, /^Файлы/, { wait: 2000 });
    check(await L.has(p, /^Анализ данных\n3/), 'файлы по предметам');
    await L.tap(p, /^Основы бизнес-анализа/, { wait: 1500 });
    check(await L.has(p, 'Лекции · 4'), 'фильтры по типам');
    await L.tap(p, /^Лекции · 4/, { wait: 1000 });
    check(!(await L.has(p, 'Практика 1')), 'фильтр «Лекции» убирает практики');
    await L.tap(p, /Лекция 2/, { wait: 1800 });
    check(await L.has(p, 'Скачать') && await L.has(p, 'Просмотр'), 'кнопки «Скачать» и «Просмотр»');
    check(await L.has(p, 'Конспект'), 'конспект лекции');
    await L.shot(p, 'robot-file');
  });

  await scenario('Помощник', {}, async (s, p) => {
    await L.tap(p, 'Учёба', { wait: 1500 });
    await L.tap(p, /^Помощник/, { wait: 1500 });
    await L.tap(p, /Чем метрика/, { wait: 3500 });
    check(await L.has(p, /стр\. 3/), 'ответ с источниками');
    await L.tap(p, /стр\. 3/, { wait: 2000 });
    check(await L.has(p, 'Страница 3 из 18'), 'источник открывает страницу лекции');
  });

  await scenario('Ещё', {}, async (s, p) => {
    await L.tap(p, 'Ещё', { wait: 1500 });
    for (const [t, want] of [['Уведомления', 'Утреннее расписание'], ['Безопасность', 'Выйти везде'], ['Группа', 'Из какой ты группы?']]) {
      await L.tap(p, t, { wait: 1800 });
      check(await L.has(p, want), `${t} открывается`);
      await L.back(p);
    }
    await L.tap(p, 'Тема и шрифт', { wait: 1500 });
    await L.tap(p, /^Аа 73 ⏎?\n?Строгий|Строгий/, { wait: 1000, optional: true });
    await L.back(p);
  });

  await scenario('Ошибка сервера', { mode: 'error' }, async (s, p) => {
    check(await L.has(p, 'Не загрузилось'), '«Не загрузилось» вместо пустоты');
    check(await L.has(p, 'Ещё раз'), 'кнопка «Ещё раз»');
    check(await L.has(p, 'Сервер сейчас не отвечает'), 'при ошибке сервера — «Сервер сейчас не отвечает», а не «проверь интернет»');
  });

  await scenario('Без сети', {}, async (s, p) => {
    await L.tap(p, 'Неделя', { wait: 1500 });
    s.state.mode = 'offline';
    await p.reload(); await p.waitForTimeout(3500); await p.evaluate(() => document.querySelector('flt-semantics-placeholder')?.click()); await p.waitForTimeout(800);
    check(await L.has(p, 'Без сети · данные от'), 'плашка «Без сети» и прошлые данные');
    check(await L.has(p, 'сегодня · 5 пар'), 'расписание видно без сети');
  });

  await scenario('Вход', { token: null }, async (s, p) => {
    check(await L.has(p, 'Войти через Telegram'), 'экран входа');
    await L.tap(p, 'Войти через Telegram', { wait: 1500 });
    check(asked(s, /\/api\/auth\/start/), 'вход через бота запрашивает код');
    await L.shot(p, 'robot-login');
  });

  const sizes = [[320, 568], [375, 667], [390, 844], [393, 852], [402, 874], [430, 932]];
  const looks = [...sizes.map((sz) => [`${sz[0]}`, { size: sz }]), ['390-dark', { size: [390, 844], dark: true }], ['430-dark', { size: [430, 932], dark: true }]];
  for (const [tag, opts] of looks) {
    await scenario('Вид: ' + tag, opts, async (s, p) => {
      await L.shot(p, `robot-${tag}-1`);
      for (const [i, t] of ['Неделя', 'Сдать', 'Учёба', 'Ещё'].entries()) { await L.tap(p, t, { wait: 1500 }); await L.shot(p, `robot-${tag}-${i + 2}`); }
      check(true, 'скрины пяти вкладок');
    });
  }

  const out = path.join(L.OUT, 'results.txt');
  fs.writeFileSync(out, results.join('\n') + '\n');
  console.log(results.join('\n'));
  const fails = results.filter((r) => r.startsWith('FAIL')).length;
  console.log(`\nOK: ${results.filter((r) => r.startsWith('OK')).length}, FAIL: ${fails}`);
  process.exitCode = fails ? 1 : 0;
})().catch((e) => { console.error(e); process.exitCode = 1; });
