"""Тёмная тема сайта /about — из светлой, автоматически.

Макет сайта светлый, а цвета в нём зашиты прямо в правилах (~60 штук).
Скрипт проходит по webapp/static/site/site.css и для каждого правила с
цветом пишет то же правило в @media (prefers-color-scheme: dark) с цветом,
у которого яркость отражена (светлое ↔ тёмное), а оттенок и насыщенность те
же. Телефон с демо (он и так тёмный) не трогаем. Блок пишется между
маркерами в конце site.css — после правок стилей запустить заново:
    python tools/site_dark.py
"""
import colorsys
import re
from pathlib import Path

CSS = Path(__file__).resolve().parent.parent / "webapp/static/site/site.css"
START, END = "/* dark:start — tools/site_dark.py */", "/* dark:end */"
SKIP = ("phone", "demo-loading", "iframe", "::selection")
COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b|(?<![-\w])(?:white|black)(?![-\w])")   # не white-space
BORDER_COLOR = re.compile(r"border(-(top|right|bottom|left))?-color\s*:")
NAMED = {"white": "#ffffff", "black": "#000000"}


def flip(c: str) -> str:
    h = NAMED.get(c.lower(), c).lstrip("#")
    if len(h) in (3, 4):
        h = "".join(x * 2 for x in h)
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    alpha = h[6:8]
    hue, light, sat = colorsys.rgb_to_hls(r, g, b)
    light = 0.085 + (1 - light) * 0.84          # бумага → почти чёрный, чернила → светлые
    if sat > 0.35 and 0.3 < light < 0.75:        # акцент (терракота) — чуть светлее, чтобы читался
        light = min(0.68, light + 0.08)
    sat = min(sat, 0.16 if light < 0.3 else 0.55)    # тёмные фоны — почти серые, без «коричневого»
    r, g, b = colorsys.hls_to_rgb(hue, light, sat)
    return "#" + "".join(f"{round(x * 255):02x}" for x in (r, g, b)) + alpha


def rules(css: str):
    """(обёртка @media или "", селектор, объявления) — плоско, с одним уровнем @media."""
    i, n = 0, len(css)
    while i < n:
        j = css.find("{", i)
        if j < 0:
            return
        head = css[i:j].strip()
        if head.startswith("@media"):
            depth, k = 1, j + 1
            while depth:
                depth += {"{": 1, "}": -1}.get(css[k], 0)
                k += 1
            for _, sel, body in rules(css[j + 1:k - 1]):
                yield head, sel, body
            i = k
        elif head.startswith("@"):
            k = css.find("}", j)
            i = k + 1
        else:
            k = css.find("}", j)
            yield "", head, css[j + 1:k]
            i = k + 1


def build(css: str) -> str:
    out = [":root{{--paper:{};--ink:{};--secondary:{};--line:{};--accent:{};--peach:{}}}".format(*tuple(
        flip(c) for c in ("#f8f6f0", "#282720", "#66635b", "#dcd8ce", "#b75438", "#eee1d3"))),
           'img[src$="capy.svg"]{filter:invert(.84) sepia(.12)}']   # капибара нарисована чернилами
    for media, sel, body in rules(css):
        if sel.startswith(":root") or any(s in sel for s in SKIP):
            continue
        decls = []
        for d in (d.strip() for d in body.split(";")):
            if COLOR.search(d) and ":" in d and "url(" not in d:
                decls.append(d)
            elif BORDER_COLOR.match(d) and any(x.startswith("border") for x in decls):
                # «border:1px solid #…» в тёмном правиле сбросил бы border-top-color:var(--accent)
                # после него (так у .spinner пропадал бегущий кусок) — повторяем и его
                decls.append(d)
        if not decls:
            continue
        rule = sel + "{" + ";".join(COLOR.sub(lambda m: flip(m.group(0)), d) for d in decls) + "}"
        out.append(media + "{" + rule + "}" if media else rule)
    return "@media (prefers-color-scheme:dark){\n" + "\n".join(out) + "\n}"


def main():
    css = CSS.read_text(encoding="utf-8")
    if START in css:
        css = css[:css.index(START)].rstrip() + "\n"
    light = css
    CSS.write_text(light + START + "\n" + build(light) + "\n" + END + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
