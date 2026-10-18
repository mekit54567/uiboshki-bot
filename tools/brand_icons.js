// Логотипы на кнопках входа (VK ID, Яндекс ID, Telegram) — PNG из официальных
// SVG в design/brands/ (откуда каждый — в комментарии файла). Перерисовать:
//   NODE_PATH=/opt/node-tools/node_modules node tools/brand_icons.js
// → app/assets/brands/<имя>.png и 2.0x/3.0x/4.0x (логический размер 24).
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const root = path.join(__dirname, '..');
const src = path.join(root, 'design', 'brands');
const out = path.join(root, 'app', 'assets', 'brands');
const SIZE = 24;

(async () => {
  const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
  const page = await browser.newPage();
  for (const file of fs.readdirSync(src).filter((f) => f.endsWith('.svg'))) {
    const svg = fs.readFileSync(path.join(src, file), 'utf8').replace(/<!--[\s\S]*?-->/g, '');
    for (const k of [1, 2, 3, 4]) {
      const px = SIZE * k;
      await page.setViewportSize({ width: px, height: px });
      await page.setContent(
        `<html><body style="margin:0;background:transparent">` +
          svg.replace('<svg ', `<svg width="${px}" height="${px}" style="display:block" `) +
          `</body></html>`,
      );
      const dir = k === 1 ? out : path.join(out, `${k}.0x`);
      fs.mkdirSync(dir, { recursive: true });
      await page.screenshot({ path: path.join(dir, file.replace('.svg', '.png')), omitBackground: true });
    }
  }
  await browser.close();
})();
