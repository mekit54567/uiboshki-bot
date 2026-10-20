// Стенд PWA на HTML (webapp/static/app-html): страница с сервера WebApp
// (uvicorn webapp.server:app), ответы /api/v1/… — из записи стенда
// webapp/static/site/demo.json (+ недостающие, как app/robot/lib.js).
// Снимки — рядом с веб-сборкой Flutter (app/build/web), чтобы сравнить.
//
//   BOT_TOKEN=1:x DATABASE_PATH=/tmp/t.db python -m uvicorn webapp.server:app --port 8099 &
//   NODE_PATH=/opt/node-tools/node_modules node tools/pwa_html_stand.js out/ [сценарий.js]
//
// Сценарий — модуль: module.exports = async ({page, shot, tap, wait}) => {...}
// По умолчанию: пять вкладок, светлая и тёмная тема.
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const REPO = path.resolve(__dirname, '..');
const BASE = process.env.STAND || 'http://localhost:8099';
const NOW = process.env.NOW || '2026-10-08T10:07:00+03:00';
const demo = JSON.parse(fs.readFileSync(path.join(REPO, 'webapp/static/site/demo.json'), 'utf8')).fx;

const extra = {
  'GET /api/meta': { api: 1, server: 'stand', min_client: { web: '0.0.0', android: '0.0.0', ios: '0.0.0' },
    login: ['telegram', 'vk', 'yandex'], features: { groups: true, sessions: true, offline: true, design2: true },
    links: { bot: 'https://t.me/UiboshkiBot', channel: 'https://t.me/kapibara_mirea', contact: '', sdo_guide: '', news: 'https://t.me/kapibara_mirea' } },
  'GET /api/auth/sessions': { items: [
    { id: 1, device: 'Капибара · iPhone', created_at: '2026-10-01 12:00:00', last_seen: '2026-10-08 10:05:00', current: true },
    { id: 2, device: 'Chrome · Windows', created_at: '2026-09-20 18:30:00', last_seen: '2026-10-06 21:14:00', current: false },
  ] },
  'GET /api/auth/identities': { items: [], available: [{ id: 'vk', name: 'VK ID' }, { id: 'yandex', name: 'Яндекс ID' }], telegram: true },
  'GET /api/auth/providers': { items: [{ id: 'vk', name: 'VK ID' }, { id: 'yandex', name: 'Яндекс ID' }] },
  'GET /api/calendar/link': { token: 'demo', ics_path: '/ics/demo' },
  // «Капибара+» как на сайте без оплаты: цены первых, касса ещё не подключена
  'GET /api/plus': { hidden: false, active: false, until: null, paid_until: null, gift: null, unlimited: false, unlimited_until: null,
    founder: false, early: true, provider: '', pay_url: '', offer_url: 'https://www.uiboshki.ru/offer', donate_url: '',
    prices: [{ plan: 'month', title: 'Месяц', days: 30, price: 149, full: 249, founder: true },
             { plan: 'semester', title: 'Семестр', days: 150, price: 649, full: 790, founder: true }],
    invite: { link: 'https://t.me/UiboshkiBot?start=ref_demo', share_text: 'Капибара — расписание, сроки и баллы МИРЭА', share_image: '',
      came: 1, rewarded: 1, bonus_days: 7, friend_days: 3, ref_max: 3, ref_counted: 1,
      ranks: { dawn: { days: 3, need_days: 1, claimed: false }, noon: { days: 5, need_days: 7, claimed: false },
        dusk: { days: 7, need_days: 14, claimed: false }, midnight: { days: 14, need_days: 21, claimed: false } } } },
  'GET /api/donate': { hidden: false, url: '', amounts: [100, 300, 500], min: 50, max: 15000,
    note: 'Это не подписка — просто спасибо. В ответ откроется роадмап: что я делаю сейчас и что дальше.', offer_url: 'https://www.uiboshki.ru/offer' },
  'GET /api/sdo/submit-rules': { accepted: ['.pdf', '.docx'], labels: ['Документ PDF', 'Документ Word'], maxfiles: 3, maxbytes: 20971520 },
};
// расписание преподавателя или группы на 3 недели — из пар своей группы (как app/robot/lib.js)
function target(type, id, title, keep) {
  const weeks = [];
  for (const monday of ['2026-10-05', '2026-10-12', '2026-10-19']) {
    const days = [];
    const m = new Date(monday + 'T12:00:00Z');
    for (let i = 0; i < 7; i++) {
      const d = new Date(m.getTime() + i * 864e5).toISOString().slice(0, 10);
      const day = demo[`GET /api/day?date=${d}`];
      const lessons = ((day && day.lessons) || []).filter(keep)
        .map((l) => ({ start: l.start, end: l.end, title: l.title, kind: l.kind, room: l.room, groups: 'УИБО-01-24, УИБО-03-24' }));
      days.push({ date: d, lessons });
    }
    weeks.push({ monday, week: demo[`GET /api/week?start=${monday}`]?.week ?? null, days });
  }
  return { type, id, title, pinned: false, today: '2026-10-08', weeks, stale: null };
}
function fallback(p) {
  if (p.startsWith('/api/target/1/')) return target(1, 4927, 'УИБО-02-24', (l) => !/Анализ/.test(l.title));
  if (p.startsWith('/api/target/')) return target(2, 77, 'Сиганьков А. А.', (l) => l.teacher === 'Сиганьков А. А.');
  if (p === '/api/day') return { lessons: [] };
  if (p === '/api/week') return { week: null, days: [] };
  if (p === '/api/notes') return { items: [] };
  if (p === '/api/search') return { items: [{ type: 2, id: 77, title: 'Сиганьков А. А.' }, { type: 1, id: 4927, title: 'УИБО-02-24' }], ready: true };
  if (p === '/api/lecture-search') return { ready: true, items: [] };
  if (p === '/api/achievements') return { items: {} };
  if (p.startsWith('/api/lesson/comments')) return { items: [], open: true, max: 500 };
  if (p.startsWith('/api/teacher/rating')) return { count: 0, avg: null, mine: null, show_min: 3, can_rate: true };
  return null;
}

async function open({ dark = false, size = [390, 844], token = 'demo-token', url = '/app-html/' } = {}) {
  const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
  const ctx = await browser.newContext({ viewport: { width: size[0], height: size[1] }, deviceScaleFactor: 2,
    isMobile: true, hasTouch: true, colorScheme: dark ? 'dark' : 'light', timezoneId: 'Europe/Moscow', locale: 'ru-RU' });
  const unknown = new Set(), errors = [];
  await ctx.addInitScript((t) => {
    if (sessionStorage.getItem('__init')) return;
    sessionStorage.setItem('__init', '1');
    localStorage.clear();
    if (t) localStorage.setItem('flutter.uib_token', JSON.stringify(t));
    localStorage.setItem('flutter.uib_toured', 'true');
  }, token);
  await ctx.route('**/api/v1/**', async (route) => {
    const r = route.request();
    const u = new URL(r.url());
    const p = u.pathname.replace('/api/v1/', '/api/');
    let key = `${r.method()} ${p}${u.search}`;
    const body = r.postData();
    if (p.startsWith('/api/sdo/goal/') && body) key += '|' + JSON.parse(body).label;
    let res = demo[key] ?? extra[key] ?? demo[`${r.method()} ${p}`] ?? extra[`${r.method()} ${p}`];
    if (res === undefined) res = fallback(p);
    if (res === undefined || res === null) { if (r.method() === 'GET') unknown.add(key); res = { ok: true }; }
    route.fulfill({ status: 200, contentType: 'application/json; charset=utf-8', body: JSON.stringify(res) });
  });
  const page = await ctx.newPage();
  page.on('pageerror', (e) => errors.push('pageerror: ' + String(e).slice(0, 300)));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text().slice(0, 300)); });
  await page.goto(BASE + url + (url.includes('?') ? '&' : '?') + 'now=' + encodeURIComponent(NOW));
  await page.waitForTimeout(1200);
  return { page, ctx, browser, unknown, errors, close: () => browser.close() };
}

async function tabs(out) {
  for (const dark of [false, true]) {
    const s = await open({ dark });
    for (let i = 0; i < 5; i++) {
      await s.page.click(`#tabbar .slot[data-i="${i}"]`);
      await s.page.waitForTimeout(900);
      await s.page.screenshot({ path: path.join(out, `tab${i}-${dark ? 'dark' : 'light'}.png`) });
    }
    console.log(dark ? 'dark' : 'light', 'unknown:', [...s.unknown].join(' | ') || '—', 'errors:', s.errors.join(' | ') || '—');
    await s.close();
  }
}

module.exports = { open };
if (require.main === module) {
  const out = process.argv[2] || 'pwa-html-out';
  fs.mkdirSync(out, { recursive: true });
  const scen = process.argv[3];
  (scen ? require(path.resolve(scen))({ open, out }) : tabs(out)).catch((e) => { console.error(e); process.exit(1); });
}
