// Скриншоты для магазинов (docs/store/screens/): веб-сборка приложения на
// записи стенда (demo.json — ничьих настоящих данных), время — четверг
// 08.10.2026 10:07. Запуск (из app/):
//   flutter build web --dart-define=API= --dart-define=NOW=2026-10-08T10:07:00+03:00
//   cd robot && node store_shots.js [appstore|rustore]
// App Store — iPhone 6.9" (1320×2868), RuStore — телефон 1080×1920; JPEG.
// Платного на снимках нет: /api/plus в записи нет — плитка «Капибара+» скрыта.
const fs = require('fs');
const path = require('path');
const L = require('./lib');

const REPO = process.env.REPO || path.resolve(__dirname, '../..');
const TARGETS = {
  appstore: { size: [440, 956], scale: 3 },   // 1320×2868
  rustore: { size: [360, 640], scale: 3 },    // 1080×1920
};

// цель по предмету — как в robot.js: с экзаменом
const goal = {};
for (const m of ['3', '4', '5']) goal[`POST /api/sdo/goal/18673|${m}`] = { ...L.demo[`POST /api/sdo/goal/18673|${m}`], exam_left: 40, best: 134 };

// ачивки уже открыты — без плашки «Новая ачивка» поверх экрана
const ACH = ['lesson', 'week_next', 'goal', 'sdo', 'widget', 'look', 'ai', 'summary', 'remind', 'teacher', 'submit',
  'week5', 'early', 'streak', 'plus', 'found', 'auto', 'clean'];
const prefs = { uib_ach: JSON.stringify(Object.fromEntries(ACH.map((id) => [id, Date.parse('2026-10-01T12:00:00+03:00')]))) };

const SCREENS = [
  ['1-today', async () => {}],
  ['2-week', async (p) => { await L.tap(p, 'Неделя', { wait: 2200 }); }],
  ['3-deadlines', async (p) => { await L.tap(p, 'Сдать', { wait: 2000 }); }],
  ['4-goal', async (p) => {
    await L.tap(p, 'Учёба', { wait: 1500 });
    await L.tap(p, /Объектно-ориентированный/, { wait: 2000 });
    await L.tap(p, 'Цель 5', { wait: 1800 });
  }],
  ['5-assistant', async (p) => {
    await L.tap(p, 'Учёба', { wait: 1500 });
    await L.tap(p, /^Помощник/, { wait: 1500 });
    await L.tap(p, /Чем метрика/, { wait: 4000 });
  }],
  ['6-more', async (p) => { await L.tap(p, 'Ещё', { wait: 2000 }); }],
];

async function one(store, name, fn, dark) {
  const t = TARGETS[store];
  const s = await L.open({ size: t.size, scale: t.scale, dark, overrides: goal, prefs });
  try {
    await fn(s.page);
    await s.page.waitForTimeout(800);
    const dir = path.join(REPO, 'docs/store/screens', store);
    fs.mkdirSync(dir, { recursive: true });
    const f = path.join(dir, `${name}${dark ? '-dark' : ''}.jpg`);
    await s.page.screenshot({ path: f, type: 'jpeg', quality: 88 });
    console.log(f, Math.round(fs.statSync(f).size / 1024) + ' КБ');
  } finally {
    await s.close();
  }
}

(async () => {
  const only = process.argv[2];
  for (const store of Object.keys(TARGETS)) {
    if (only && only !== store) continue;
    for (const [name, fn] of SCREENS) await one(store, name, fn, false);
    // пара тёмных: сегодня и неделя
    for (const [name, fn] of SCREENS.slice(0, 2)) await one(store, name, fn, true);
  }
})().catch((e) => { console.error(e); process.exitCode = 1; });
