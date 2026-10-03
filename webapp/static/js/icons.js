// Свои иконки WebApp вместо эмодзи — часть WebApp (владелец: «перерисовать все
// стикеры под дизайн приложения»). Эмодзи на iPhone, Android и компьютере
// выглядят по-разному и иногда не рисуются вовсе; эти — одна тонкая линия,
// цвет берут из темы (currentColor). Спрайт вставляется в страницу один раз,
// дальше <svg><use href="#i-имя"></svg> — и в разметке, и в icon() из JS.
// Файлы подключаются по порядку и делят глобальную область видимости.

const ICON_PATHS = {
  today: '<rect x="3.5" y="5" width="17" height="15.5" rx="3.5"/><path d="M3.5 10h17M8 3v4M16 3v4"/><circle cx="12" cy="15" r="1.6" fill="currentColor" stroke="none"/>',
  deadlines: '<rect x="4.5" y="4" width="15" height="17" rx="3.5"/><path d="M9 3h6v3H9zM8.5 11.5l1.6 1.6 3-3M8.5 17h7"/>',
  folder: '<path d="M3.5 7.5A2.5 2.5 0 0 1 6 5h3.6l2 2.2H18a2.5 2.5 0 0 1 2.5 2.5v7.8A2.5 2.5 0 0 1 18 20H6a2.5 2.5 0 0 1-2.5-2.5z"/><path d="M3.5 10.5h17"/>',
  chat: '<path d="M5 18.5 3.8 21l3.4-1.6A9 9 0 1 0 5 18.5z"/><path d="M12 8.2l.9 2 2 .9-2 .9-.9 2-.9-2-2-.9 2-.9z" fill="currentColor"/>',
  message: '<path d="M5 18.5 3.8 21l3.4-1.6A9 9 0 1 0 5 18.5z"/><path d="M8.5 10.5h7M8.5 14h4.5"/>',
  more: '<rect x="4" y="4" width="6.5" height="6.5" rx="2"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="2"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="2"/><circle cx="16.75" cy="16.75" r="3.3"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5"/>',
  cap: '<path d="M2.5 9.5 12 5l9.5 4.5L12 14z"/><path d="M6.5 11.5v4.2c0 1.6 2.5 3 5.5 3s5.5-1.4 5.5-3v-4.2M21.5 9.5v5"/>',
  calendar: '<rect x="3.5" y="5" width="17" height="15.5" rx="3.5"/><path d="M3.5 10h17M8 3v4M16 3v4M8 14h2M14 14h2M8 17h2"/>',
  calsub: '<rect x="3.5" y="5" width="17" height="15.5" rx="3.5"/><path d="M3.5 10h17M8 3v4M16 3v4M12 13v5M9.5 15.5h5"/>',
  phone: '<rect x="6.5" y="2.5" width="11" height="19" rx="3"/><path d="M10.5 18.5h3M12 7v6.5M9.5 11l2.5 2.5 2.5-2.5"/>',
  download: '<path d="M12 4v11M7.5 10.5 12 15l4.5-4.5M5 19.5h14"/>',
  upload: '<path d="M12 15.5V4.5M7.5 9 12 4.5 16.5 9M5 19.5h14"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  checkCircle: '<circle cx="12" cy="12" r="8.5"/><path d="m8.2 12.3 2.6 2.6 5-5.2"/>',
  cross: '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
  clock: '<circle cx="12" cy="12" r="8"/><path d="M12 7.5V12l3 2"/>',
  lock: '<rect x="5" y="10.5" width="14" height="10" rx="3"/><path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5"/>',
  shield: '<path d="M12 3.5 5 6v5.5c0 4.2 2.9 7.6 7 9 4.1-1.4 7-4.8 7-9V6z"/><path d="m9 12 2.2 2.2L15.5 10"/>',
  classroom: '<path d="M3.5 20.5h17M5 20.5V10l7-5 7 5v10.5M10 20.5v-5h4v5"/>',
  doc: '<path d="M14 3.5H8A2.5 2.5 0 0 0 5.5 6v12A2.5 2.5 0 0 0 8 20.5h8a2.5 2.5 0 0 0 2.5-2.5V8z"/><path d="M14 3.5V8h4.5M9 13h6M9 16.5h4"/>',
  table: '<rect x="4" y="4.5" width="16" height="15" rx="3"/><path d="M4 9.5h16M4 14.5h16M10 9.5v10"/>',
  slides: '<rect x="3.5" y="4.5" width="17" height="12" rx="2.5"/><path d="M12 16.5v3.5M8.5 20h7M8 12.5l3-3 2 2 3-3"/>',
  image: '<rect x="3.5" y="4.5" width="17" height="15" rx="3"/><circle cx="9" cy="10" r="1.8"/><path d="m4 17.5 4.5-4.5 3.5 3.5 2.5-2.5 5.5 5"/>',
  archive: '<rect x="4" y="3.5" width="16" height="17" rx="3"/><path d="M12 3.5v2M12 7.5v2M12 11.5v2"/><rect x="10" y="14.5" width="4" height="3" rx="1"/>',
  book: '<path d="M4.5 5.5A2 2 0 0 1 6.5 3.5H19v14H6.5a2 2 0 0 0-2 2z"/><path d="M4.5 19.5a2 2 0 0 0 2 1.5H19v-3.5"/>',
  bookOpen: '<path d="M12 6.5C10.3 5 7.8 4.5 4 4.5v13c3.8 0 6.3.5 8 2 1.7-1.5 4.2-2 8-2v-13c-3.8 0-6.3.5-8 2z"/><path d="M12 6.5v13"/>',
  note: '<path d="M5.5 5.5A2 2 0 0 1 7.5 3.5h9a2 2 0 0 1 2 2V15l-5.5 5.5H7.5a2 2 0 0 1-2-2z"/><path d="M13 20.5V16a1 1 0 0 1 1-1h4.5M9 8.5h6M9 12h4"/>',
  pin: '<path d="M14.5 3.5 20.5 9.5l-2.5 1-3.5 3.5.5 4-1.5 1.5-3.5-3.5L5 21l-.5-.5L9.5 15 6 11.5 7.5 10l4 .5L15 7z"/>',
  place: '<path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0C18.5 15.4 12 21 12 21z"/><circle cx="12" cy="10" r="2.4"/>',
  user: '<circle cx="12" cy="8.5" r="3.8"/><path d="M4.8 20c.8-3.6 3.6-5.6 7.2-5.6s6.4 2 7.2 5.6"/>',
  users: '<circle cx="9" cy="9" r="3.4"/><path d="M3 19.5c.6-3.2 3-5 6-5s5.4 1.8 6 5"/><path d="M15.5 6a3.2 3.2 0 0 1 0 6.2M17.5 14.7c1.8.6 3.1 2.2 3.5 4.8"/>',
  door: '<path d="M5.5 20.5h13M7 20.5V5a1.5 1.5 0 0 1 1.5-1.5h7A1.5 1.5 0 0 1 17 5v15.5"/><circle cx="14" cy="12.5" r=".9" fill="currentColor"/>',
  edit: '<path d="M15.5 4.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4z"/><path d="M13.5 6.5l3 3"/>',
  trash: '<path d="M4.5 7h15M9.5 7V4.5h5V7M6.5 7l1 12.5a1.5 1.5 0 0 0 1.5 1.5h6a1.5 1.5 0 0 0 1.5-1.5l1-12.5M10 11v6M14 11v6"/>',
  undo: '<path d="M9 14.5 4.5 10 9 5.5"/><path d="M4.5 10H14a5.5 5.5 0 0 1 0 11h-3"/>',
  link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
  clip: '<path d="m19.5 11.5-7.4 7.4a4.8 4.8 0 0 1-6.8-6.8l7.7-7.7a3.2 3.2 0 0 1 4.5 4.5l-7.5 7.5a1.6 1.6 0 0 1-2.3-2.3l6.9-6.9"/>',
  send: '<path d="M20.5 3.5 3.5 10.6l6.8 2.6 2.6 6.8z"/><path d="m10.3 13.2 4.6-4.6"/>',
  camera: '<path d="M4 8.5A2 2 0 0 1 6 6.5h2l1.5-2h5l1.5 2h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z"/><circle cx="12" cy="13" r="3.5"/>',
  warning: '<path d="M10.3 4.7 3 17.5A2 2 0 0 0 4.7 20.5h14.6a2 2 0 0 0 1.7-3L13.7 4.7a2 2 0 0 0-3.4 0z"/><path d="M12 9.5v4M12 17h.01"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19 12a7 7 0 0 0-.1-1.2l2-1.5-2-3.4-2.3.9a7 7 0 0 0-2.1-1.2L14 3h-4l-.5 2.6a7 7 0 0 0-2.1 1.2l-2.3-.9-2 3.4 2 1.5a7 7 0 0 0 0 2.4l-2 1.5 2 3.4 2.3-.9a7 7 0 0 0 2.1 1.2L10 21h4l.5-2.6a7 7 0 0 0 2.1-1.2l2.3.9 2-3.4-2-1.5c.1-.4.1-.8.1-1.2z"/>',
  sparkle: '<path d="M12 3.5l1.9 5.1 5.1 1.9-5.1 1.9L12 17.5l-1.9-5.1L5 10.5l5.1-1.9z"/><path d="M18.5 16l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7z" fill="currentColor"/>',
  medal: '<path d="M8 3.5h8l-2 5h-4z"/><circle cx="12" cy="14.5" r="5.5"/><path d="m12 12 .9 1.8 2 .3-1.4 1.4.3 2-1.8-.9-1.8.9.3-2-1.4-1.4 2-.3z"/>',
  pulse: '<path d="M3 12h4l2-5 4 10 2-5h6"/>',
  refresh: '<path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3"/><path d="M19.5 4.5v4.2h-4.2"/>',
  back: '<path d="M14.5 5.5 8 12l6.5 6.5"/>',
  chevron: '<path d="M9.5 5.5 16 12l-6.5 6.5"/>',
  copy: '<rect x="8.5" y="8.5" width="12" height="12" rx="2.5"/><path d="M15.5 8.5V6A2.5 2.5 0 0 0 13 3.5H6A2.5 2.5 0 0 0 3.5 6v7A2.5 2.5 0 0 0 6 15.5h2.5"/>',
  party: '<path d="M4 20.5 8.7 8.3l7 7z"/><path d="M8.7 8.3c1.8 1.6 4.5 4.3 7 7M6.4 14.4l3.2 3.2"/><path d="M13.5 3.5c.4 1.8 1.6 2.6 3 2.5M20.5 10.5c-1.8-.4-2.6.4-2.8 2M16.5 3v1.2M20.5 6.5h1.5M13 8.5l1-1"/>',
  wave: '<path d="M8.2 13.5V6.3a1.4 1.4 0 0 1 2.8 0V11.5M11 11V4.4a1.4 1.4 0 0 1 2.8 0v7M13.8 11.5V6.2a1.4 1.4 0 0 1 2.8 0v7.6a6.2 6.2 0 0 1-6.2 6.2h-.3a6 6 0 0 1-4.7-2.3l-2.3-3a1.4 1.4 0 0 1 2.2-1.8L8.2 15"/><path d="M18.8 3.6a5 5 0 0 1 2 2.8M3.6 6.4a5 5 0 0 1 2-2.8"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  bell: '<path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 1.5h-15z"/><path d="M10 20.5a2 2 0 0 0 4 0"/>',
  route: '<circle cx="6" cy="18" r="2.2"/><circle cx="18" cy="6" r="2.2"/><path d="M8.2 18H15a3 3 0 0 0 0-6H9a3 3 0 0 1 0-6h6.8"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4"/>',
};

// Капибара с логотипа бота (силуэт, заливкой) — на кнопке СДО, когда вход
// подключён (more.js: loadSdoStatus). Своя рамка, не 24×24 линией.
const CAPY_SYMBOL = '<symbol id="i-capy" viewBox="55 40 400 430"><path fill="currentColor" stroke="none" d="M321 450l-36 13-39 3-8-3 2-5 13-11 29-3 21-6 6 0 13 7zM164 387l5-2 25 11 23 7 21 33 1 8-16 13-27-7-30-23-12-19-1-9zM382 375l-4 16-19 30-13 11-6 3-25-5-1-5 7-18 4-24 18-12 21-21 6 1 11 5zM233 295l3 26 4 5 16 15 4 13-1 6-6 6-32 26-21-5-27-13-4-11-6-23-1-18 4-7 19-20 19-12zM306 268l18 7 22 12 5 8 6 25 1 20-15 17-25 17-6-1-38-15-5-11 1-6 19-7 14-20 0-9-8-31 0-5 3-2zM194 275l-15 11-23 24-11-2-1-5 2-5 20-29 24-25 6-4 4 1zM295 229l27 16 27 10 10 9 0 5-5 5-6 1-47-20-10-16-1-10zM411 91l2 15 10 16 22 68 5 35 0 17-5 11-18 15-12 5-9 3-16-1-18-11-18-17-40-16-27-19-5 9-2 15 7 49 7 25-10 17-10 0-7 4-9 0-4-6-8-7-5-40-7-19-29-33-7 1-12 9-22 22-15 18-11 17-12 28-3 12 2 14 9 13 14 10 2 3-2 7-8 6-5 8-6 1-10-2-7 5-9-1-12-21-9-31-5-33-1-42-11-33-4-24 1-37 7-26 15-32 19-24 20-18 29-17 19-7 31-6 33 0 28 5 42 12 44 16 4 0 11-9 4 4 5 14 11 4 5-1 5-15 10 5zM403 242l0 8 6 7 6 0 2-5-3-11-8-3zM385 171l8 8 2-3-6-17-4-1z"/></symbol>';

(function injectIconSprite() {
  const symbols = Object.keys(ICON_PATHS).map(k => '<symbol id="i-' + k + '" viewBox="0 0 24 24">' + ICON_PATHS[k] + '</symbol>').join("") + CAPY_SYMBOL;
  document.body.insertAdjacentHTML("afterbegin",
    '<svg width="0" height="0" style="position:absolute" aria-hidden="true"><defs>' + symbols + '</defs></svg>');
})();

function icon(name, cls) {
  return '<svg class="ico' + (cls ? " " + cls : "") + '" aria-hidden="true"><use href="#i-' + name + '"/></svg>';
}

// Тип файла — иконкой и цветом (PDF красный, таблицы зелёные, Word синий…)
function fileTypeIcon(name) {
  const ext = ((name || "").split(".").pop() || "").toLowerCase();
  const t = { pdf: ["doc", "pdf"], doc: ["doc", "word"], docx: ["doc", "word"], odt: ["doc", "word"], txt: ["doc", ""], rtf: ["doc", "word"],
    xls: ["table", "xls"], xlsx: ["table", "xls"], csv: ["table", "xls"], ods: ["table", "xls"],
    ppt: ["slides", "ppt"], pptx: ["slides", "ppt"], odp: ["slides", "ppt"],
    png: ["image", "img"], jpg: ["image", "img"], jpeg: ["image", "img"], gif: ["image", "img"], webp: ["image", "img"], heic: ["image", "img"],
    zip: ["archive", ""], rar: ["archive", ""], "7z": ["archive", ""] }[ext] || ["doc", ""];
  return '<span class="ftype ' + t[1] + '">' + icon(t[0]) + '</span>';
}
