// Робот-проверка приложения «Капибара»: веб-сборка Flutter + ответы API из
// записи стенда сайта (webapp/static/site/demo.json) + недостающие ответы.
// Запуск — см. robot.js; в CI — .github/workflows/app-robot.yml.
const http = require('http');
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const REPO = process.env.REPO || path.resolve(__dirname, '../..');
const WEB = path.join(REPO, 'app/build/web');
const OUT = process.env.ROBOT_OUT || path.join(__dirname, 'out');
const SHOTS = path.join(OUT, 'shots');
fs.mkdirSync(SHOTS, { recursive: true });

const demo = JSON.parse(fs.readFileSync(path.join(REPO, 'webapp/static/site/demo.json'), 'utf8')).fx;

// --- недостающие в demo.json ответы, по форме настоящих обработчиков ---
function teacherTarget(teacher, id) {
  const weeks = [];
  for (const monday of ['2026-10-05', '2026-10-12', '2026-10-19']) {
    const days = [];
    const m = new Date(monday + 'T12:00:00Z');
    for (let i = 0; i < 7; i++) {
      const d = new Date(m.getTime() + i * 864e5).toISOString().slice(0, 10);
      const day = demo[`GET /api/day?date=${d}`];
      const lessons = ((day && day.lessons) || []).filter((l) => l.teacher === teacher)
        .map((l) => ({ start: l.start, end: l.end, title: l.title, kind: l.kind, room: l.room, groups: 'УИБО-01-24, УИБО-03-24' }));
      days.push({ date: d, lessons });
    }
    weeks.push({ monday, week: demo[`GET /api/week?start=${monday}`]?.week ?? null, days });
  }
  return { type: 2, id, title: teacher, pinned: false, today: '2026-10-08', weeks, stale: null };
}

const extra = {
  'GET /api/meta': { api: 1, server: '5.59.6', min_client: { web: '0.0.0', android: '0.0.0', ios: '0.0.0' }, login: ['telegram', 'vk', 'yandex'], features: { groups: true, sessions: true, offline: true }, links: { bot: 'https://t.me/UiboshkiBot', channel: 'https://t.me/uiboshki', contact: '', sdo_guide: '' } },
  'GET /api/auth/sessions': { items: [
    { id: 1, device: 'Капибара · iPhone', created_at: '2026-10-01 12:00:00', last_seen: '2026-10-08 10:05:00', current: true },
    { id: 2, device: 'Chrome · Windows', created_at: '2026-09-20 18:30:00', last_seen: '2026-10-06 21:14:00', current: false },
  ] },
  'GET /api/auth/identities': { items: [], available: [{ id: 'vk', name: 'VK ID' }, { id: 'yandex', name: 'Яндекс ID' }], telegram: true },
  'GET /api/auth/providers': { items: [{ id: 'vk', name: 'VK ID' }, { id: 'yandex', name: 'Яндекс ID' }] },
  'GET /api/calendar/link': { token: 'demo', ics_path: '/ics/demo' },
  'GET /api/target/2/77': teacherTarget('Сиганьков А. А.', 77),
  'GET /api/sdo/submit-rules': { accepted: ['.pdf', '.docx'], labels: ['Документ PDF', 'Документ Word'], maxfiles: 3, maxbytes: 20971520 },
};

function fallback(method, p) {
  if (p === '/api/day') return { lessons: [] };
  if (p === '/api/week') return { week: null, days: [] };
  if (p === '/api/notes') return { items: [] };
  if (p === '/api/search') return { items: [{ type: 2, id: 77, title: 'Сиганьков А. А.' }, { type: 1, id: 4927, title: 'УИБО-02-24' }, { type: 3, id: 900, title: 'А-17 (В-78)' }], ready: true };
  if (p === '/api/lecture-search') return { ready: true, items: [] };
  if (p === '/api/achievements') return { items: {} };
  if (p === '/api/groups/search') return { items: [{ id: 4928, name: 'УИБО-03-24' }, { id: 4927, name: 'УИБО-02-24' }] };
  if (p === '/api/auth/start') return { code: 'abc', link: 'https://t.me/UiboshkiBot?start=login_abc', pick: 47 };
  if (p === '/api/auth/poll') return { status: 'wait' };
  if (p === '/api/sdo/submit') return { status: 'Отправлено для оценивания' };
  if (p.startsWith('/api/target/')) return teacherTarget('Сиганьков А. А.', 77);
  return null;
}

// --- статический сервер сборки ---
function serve() {
  const types = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.json': 'application/json', '.wasm': 'application/wasm', '.png': 'image/png', '.otf': 'font/otf', '.ttf': 'font/ttf', '.css': 'text/css', '.svg': 'image/svg+xml' };
  const srv = http.createServer((req, res) => {
    let u = decodeURIComponent(req.url.split('?')[0]);
    if (u === '/' || u === '/app' || u === '/app/') u = '/index.html';
    const f = path.join(WEB, u);
    fs.readFile(f, (e, b) => {
      if (e) { res.writeHead(404); return res.end(); }
      res.writeHead(200, { 'content-type': types[path.extname(f)] || 'application/octet-stream' });
      res.end(b);
    });
  });
  return new Promise((ok) => srv.listen(0, () => ok({ srv, url: `http://127.0.0.1:${srv.address().port}` })));
}

/**
 * opts: { dark, size:[w,h], token, toured, mode: 'ok'|'empty'|'error'|'slow', overrides, scale, prefs }
 */
async function open(opts = {}) {
  const { srv, url } = await serve();
  const browser = await chromium.launch();
  const [w, h] = opts.size || [390, 844];
  const ctx = await browser.newContext({
    viewport: { width: w, height: h }, deviceScaleFactor: opts.scale || 2, isMobile: true, hasTouch: true,
    colorScheme: opts.dark ? 'dark' : 'light', timezoneId: 'Europe/Moscow', locale: 'ru-RU',
  });
  const log = { unknown: new Set(), errors: [], asked: [], bodies: [] };
  const token = opts.token === undefined ? 'demo-token' : opts.token;
  await ctx.addInitScript(([t, toured, prefs]) => {
    if (sessionStorage.getItem('__init')) return;
    sessionStorage.setItem('__init', '1');
    localStorage.clear();
    if (t) localStorage.setItem('flutter.uib_token', JSON.stringify(t));
    if (toured) localStorage.setItem('flutter.uib_toured', 'true');
    for (const [k, v] of Object.entries(prefs)) localStorage.setItem('flutter.' + k, JSON.stringify(v));
  }, [token, opts.toured !== false, opts.prefs || {}]);
  const state = { mode: opts.mode || 'ok', overrides: opts.overrides || {} };
  await ctx.route('**/api/v1/**', async (route) => {
    const r = route.request();
    const u = new URL(r.url());
    const p = u.pathname.replace('/api/v1/', '/api/');
    let key = `${r.method()} ${p}${u.search}`;
    const body = r.postData();
    if (p.startsWith('/api/sdo/goal/') && body) key += '|' + JSON.parse(body).label;
    log.asked.push(key);
    if (body && r.method() !== 'GET') log.bodies.push([key, body]);
    if (state.mode === 'slow') await new Promise((x) => setTimeout(x, 4000));
    if (state.mode === 'error' && !p.startsWith('/api/auth/')) return route.fulfill({ status: 500, contentType: 'text/plain', body: 'Internal Server Error' }); // как необработанная ошибка FastAPI
    if (state.mode === 'offline') return route.abort('internetdisconnected');
    let res = key in state.overrides ? state.overrides[key] : (demo[key] ?? extra[key] ?? extra[`${r.method()} ${p}`]);
    if (res === undefined) res = fallback(r.method(), p);
    // новый дизайн (5.79, «Оформление») робот проверяет включённым, как на сервере
    if (p === '/api/meta' && res?.features) res = { ...res, features: { design2: true, ...res.features } };
    if (res === undefined || res === null) {
      if (r.method() === 'GET') log.unknown.add(key);
      res = { ok: true };
    }
    if (state.mode === 'empty' && r.method() === 'GET') res = emptied(p, res);
    route.fulfill({ status: 200, contentType: 'application/json; charset=utf-8', body: JSON.stringify(res) });
  });
  const page = await ctx.newPage();
  page.on('console', (m) => { if (m.type() === 'error' || /exception|error/i.test(m.text())) log.errors.push(m.text().slice(0, 400)); });
  page.on('pageerror', (e) => log.errors.push('pageerror: ' + String(e).slice(0, 400)));
  await page.goto(url + (opts.path || '/app'));
  await page.waitForTimeout(2500);
  if (opts.semantics !== false) await enableSemantics(page);
  const close = async () => { await browser.close(); srv.close(); };
  return { page, ctx, log, state, close, url };
}

function emptied(p, res) {
  if (p === '/api/today') return { ...res, lessons: [] };
  if (p === '/api/me') return res;
  if (p === '/api/sdo/status') return { state: 'none' };
  const out = { ...res };
  for (const k of Object.keys(out)) if (Array.isArray(out[k])) out[k] = [];
  return out;
}

async function enableSemantics(page) {
  await page.evaluate(() => {
    const ph = document.querySelector('flt-semantics-placeholder');
    if (ph) ph.click();
  });
  await page.waitForTimeout(600);
}

// --- поиск по дереву доступности Flutter ---
async function nodes(page) {
  return page.evaluate(() => {
    const out = [];
    for (const el of document.querySelectorAll('flt-semantics')) {
      const r = el.getBoundingClientRect();
      if (r.width < 1 || r.height < 1) continue;
      const own = [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join('').trim();
      const label = (el.getAttribute('aria-label') || own || el.querySelector(':scope > span')?.textContent || '').trim();
      if (!label) continue;
      out.push({ label, role: el.getAttribute('role') || '', x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) });
    }
    return out;
  });
}

async function dump(page, title = '') {
  const n = await nodes(page);
  console.log(`--- ${title} (${n.length})`);
  for (const x of n) console.log(`${x.role.padEnd(8)} ${String(x.x).padStart(4)},${String(x.y).padStart(4)} ${x.w}x${x.h}  ${x.label.replace(/\n/g, ' ⏎ ').slice(0, 110)}`);
}

/** Нажать на элемент по тексту (точно или по регулярке); nth — какой по счёту. */
async function tap(page, text, { nth = 0, wait = 900, optional = false } = {}) {
  const n = (await nodes(page)).filter((x) => (text instanceof RegExp ? text.test(x.label) : x.label === text));
  if (!n[nth]) {
    if (optional) return false;
    throw new Error(`нет на экране: ${text}`);
  }
  const t = n[nth];
  await page.mouse.click(t.x + t.w / 2, t.y + Math.min(t.h / 2, 22));
  await page.waitForTimeout(wait);
  return true;
}

async function has(page, text) {
  return (await nodes(page)).some((x) => (text instanceof RegExp ? text.test(x.label) : x.label.includes(text)));
}

async function shot(page, name) {
  const f = path.join(SHOTS, name + '.png');
  await page.screenshot({ path: f });
  return f;
}

// Палец, а не мышь: Flutter листает только касанием. События — прямо в
// странице: через CDP в медленном облаке шаг идёт ~300 мс, и Flutter видит
// «медленный» жест без скорости (свайп недели не срабатывал из-за стенда).
async function swipe(page, { from = [0.85, 0.5], to = [0.15, 0.5], steps = 8, dt = 12 } = {}) {
  const v = page.viewportSize();
  await page.evaluate(async ([a, b, steps, dt]) => {
    const el = document.elementFromPoint(a[0], a[1]);
    const opt = (x, y) => ({ pointerId: 7, pointerType: 'touch', isPrimary: true, bubbles: true, cancelable: true, composed: true, clientX: x, clientY: y, buttons: 1, pressure: 0.5 });
    el.dispatchEvent(new PointerEvent('pointerdown', opt(a[0], a[1])));
    for (let i = 1; i <= steps; i++) {
      const t0 = performance.now(); while (performance.now() - t0 < dt) {} // без отдачи кадра: стенд медленный
      const k = i / steps;
      el.dispatchEvent(new PointerEvent('pointermove', opt(a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k)));
    }
    el.dispatchEvent(new PointerEvent('pointerup', { ...opt(b[0], b[1]), buttons: 0, pressure: 0 }));
  }, [[v.width * from[0], v.height * from[1]], [v.width * to[0], v.height * to[1]], steps, dt]);
  await page.waitForTimeout(1300);
}

async function scroll(page, dy = 400, at = 0.6) {
  const v = page.viewportSize();
  await swipe(page, { from: [0.5, at], to: [0.5, at - dy / v.height], steps: 8 });
}

async function back(page) {
  // кнопка «назад» AppBar или системная — у Flutter web это history.back
  if (await tap(page, /^(Back|Назад|Закрыть|Close)$/, { optional: true })) return true;
  await page.keyboard.press('Escape'); // лист снизу закрывается Escape
  await page.waitForTimeout(800);
  return false;
}

module.exports = { open, nodes, dump, tap, has, shot, swipe, scroll, back, demo, SHOTS, OUT };

/** Ввести текст в поле по координатам (поля Flutter видны браузеру только в фокусе). */
async function type(page, x, y, text) {
  await page.mouse.click(x, y);
  await page.waitForTimeout(500);
  await page.keyboard.type(text, { delay: 25 });
  await page.waitForTimeout(1200);
}
module.exports.type = type;
