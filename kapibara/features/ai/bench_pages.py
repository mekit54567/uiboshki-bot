"""Страницы /aitest (часть bench.py, выбор модели ИИ): отчёт отбора с ценами
и баллами, слепое голосование финалистов, итог текстом и хранение страниц в
settings. Отдаёт их webapp/routes/aitest.py по подписанной ссылке; снаружи
имена берут через `kapibara.features.ai.bench` — там они те же объекты."""

import base64
import json
import re
from collections import Counter

RUB = 85                                                    # ₽ за $ — для таблицы
VOTE_KEY, VOTE_PICKS = "aitest:key", "aitest:picks"     # кто за каким ответом; выбор на сервере
SETTINGS = {"vote": "aitest:html", "report": "aitest:report"}


# ── Страницы ────────────────────────────────────────────────────────────────

def _answer_html(text: str) -> str:
    from kapibara.core.utils import md_to_tg_html_chunks
    return "\n".join(md_to_tg_html_chunks(text)).replace("\n", "<br>")


CSS = """body{margin:0;padding:16px;font:15px/1.5 -apple-system,system-ui,sans-serif;background:#f4f1ea;color:#24221d}
h1{font-size:24px;margin:0 0 4px}.lead{color:#6c675d;margin:0 0 18px}
section{background:#fffdf8;border-radius:18px;padding:14px;margin-bottom:16px;box-shadow:0 1px 0 #e3ddd0}
.k{margin:0;color:#b75438;font-size:12px;font-weight:700;text-transform:uppercase}h2{font-size:16px;margin:4px 0 10px;overflow-wrap:anywhere}
.a{border:1.5px solid #e3ddd0;border-radius:14px;padding:10px 12px;margin-top:8px}.a.on{border-color:#b75438;background:#fbf1ea}
.h{display:flex;justify-content:space-between;align-items:center;gap:8px;overflow-wrap:anywhere}.t{font-size:14px;margin-top:6px;overflow-wrap:anywhere}.t pre{white-space:pre-wrap}
button{font:600 14px system-ui;border:0;border-radius:10px;padding:10px 16px;background:#24221d;color:#fff}
.t.cut{max-height:360px;overflow:hidden;-webkit-mask-image:linear-gradient(#000 75%,transparent)}
.more{margin-top:6px;background:transparent;color:#b75438;padding:6px 0}
.m{font-size:12px;color:#b75438;font-weight:700;margin-top:6px}#res{white-space:pre-wrap;font:14px/1.6 ui-monospace,monospace}
.bar{position:sticky;bottom:0;background:#f4f1ea;padding:10px 0}
.row{display:grid;grid-template-columns:1fr auto;gap:2px 10px;padding:10px 0;border-top:1px solid #e3ddd0;overflow-wrap:anywhere}
.row b{font-size:15px}.n{font:700 18px ui-monospace,monospace;text-align:right}.sub{grid-column:1/-1;font-size:13px;color:#6c675d}
.base{background:#fbf1ea;border-radius:10px;padding:10px}summary{cursor:pointer;font-weight:600;overflow-wrap:anywhere}
@media (prefers-color-scheme:dark){body,.bar{background:#1b1a17;color:#ece8df}section{background:#25231f;box-shadow:none}
.a,.row{border-color:#3a362f}.a.on,.base{background:#3a2a22}.lead,.sub{color:#a59f93}button{background:#ece8df;color:#1b1a17}.more{background:transparent;color:#e08a6c}}"""


def report_page(rows: list[dict], tasks: list[dict], judge: str | None, cost: float) -> str:
    """Страница отбора: модели с баллами и ценой, под ней — ответы по задачам."""
    from kapibara.core.utils import esc
    out = []
    for r in rows:
        flags = ", ".join(f"{k} ×{v}" for k, v in sorted(r["flags"].items(), key=lambda kv: -kv[1]))
        bits = [f"{r['q_rub']} ₽ за 1000 вопросов", f"{r['secs']} с",
                f"конспект {r['s_score'] if r['s_score'] is not None else '—'}",
                f"намерения {r['intent']}%" if r["intent"] is not None else "",
                "видит фото" if r["image"] else "без фото",
                f"ошибок {r['errors']}" if r["errors"] else "", flags]
        out.append(f'<div class="row{" base" if r["baseline"] else ""}"><b>{"★ " if r["star"] else ""}{esc(r["name"])}'
                   f'{" · сейчас у нас" if r["baseline"] else ""}</b><span class="n">{r["q_score"] if r["q_score"] is not None else "—"}</span>'
                   f'<span class="sub">{esc(r["id"])} · {esc(" · ".join(b for b in bits if b))}</span></div>')
    names = {r["id"]: r["name"] for r in rows}
    blocks = []
    for n, t in enumerate(tasks):
        if t["kind"] == "Намерение":
            continue
        ans = sorted(t["answers"].items(), key=lambda kv: -(kv[1].get("score") or 0))
        inner = "".join(
            f'<div class="a"><div class="h"><b>{esc(names.get(m, m))}</b><span>{a.get("score", "—")}</span></div>'
            f'<div class="m">{esc(" · ".join(a["flags"]))}{" · " if a["flags"] else ""}${a["cost"]:.5f} · {a["secs"]:.1f} с</div>'
            f'<div class="t">{_answer_html(a["text"][:4000])}</div></div>' for m, a in ans)
        blocks.append(f'<section><details><summary>{t["kind"]} {n + 1} · {esc(t["subject"] or "без предмета")}: '
                      f'{esc(t["title"][:200])}</summary>{inner}</details></section>')
    wrong = [f"{esc(t['title'])} → нужно {t['want']}: ошиблись "
             + ", ".join(esc(names.get(m, m)) for m, a in t["answers"].items() if a.get("intent") != t["want"])
             for t in tasks if t["kind"] == "Намерение" and any(a.get("intent") != t["want"] for a in t["answers"].values())]
    intents = (f'<section><p class="k">Классификатор намерений</p>{"<br>".join(wrong) or "Все модели — без ошибок."}</section>'
               if any(t["kind"] == "Намерение" for t in tasks) else "")
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light dark">
<title>Отбор моделей ИИ</title><style>{CSS}</style></head><body><h1>Отбор моделей ИИ</h1>
<p class="lead">Балл — средняя оценка судьи ({esc(judge or "нет")}) за ответы на вопросы группы, 1–10, ошибка — 0.
★ — лучшие за свои деньги: никто не отвечает лучше и дешевле сразу. Цена — по счёту OpenRouter, ₽ по {RUB} за $.
Прогон стоил ${cost:.2f}. Финалистов — в слепое голосование: <code>/aitest vote id1 id2 …</code></p>
<section>{"".join(out)}</section>{intents}{"".join(blocks)}</body></html>"""


def report_text(page_html: str, cut: int = 150, full: str = "") -> str:
    """Отбор текстом (&view=text) — для Claude: полная страница с ответами
    слишком длинная, чтение по ссылке обрывается на середине. Ответы — по
    первым cut символов, баллы, цена и пометки — целиком; ответы модели, в
    имени которой есть full (&full=ling), — целиком: разобрать их подробно."""
    import html as html_lib

    def plain(fragment: str) -> str:
        return html_lib.unescape(re.sub(r"<[^>]+>", "", re.sub(r"<br>", "\n", fragment))).strip()

    def short(m: re.Match) -> str:
        name, answer = m.group(1), m.group(3)
        if full and full.lower() in plain(name).lower():
            text = plain(answer)
        else:
            text = re.sub(r"\s+", " ", html_lib.unescape(re.sub(r"<[^>]+>", " ", answer))).strip()
            text = text[:cut] + ("…" if len(text) > cut else "")
        return f'<div class="a"><b>{name}</b>{m.group(2)}<div class="t">{html_lib.escape(text)}</div></div>'

    body = page_html.split("<body>", 1)[-1]
    body = re.sub(r'<div class="a"><div class="h"><b>(.*?)</b>(.*?)<div class="t">(.*?)</div></div>',
                  short, body, flags=re.S)
    body = re.sub(r"<br>|</div>|</section>|</summary>|</p>|</h1>", "\n", body)
    body = re.sub(r'<span class="(n|sub)">', " | ", body)
    text = html_lib.unescape(re.sub(r"<[^>]+>", "", body))
    return re.sub(r"\n\s*\n+", "\n", text).strip() + "\n"


def vote_key(items: list[dict], names: dict[str, str]) -> dict:
    """Ключ слепого теста: какой модели какой ответ в каждом блоке (порядок —
    как на странице), её цена и время; заголовки — для итога."""
    return {"names": names, "blocks": [
        {"kind": it["kind"], "subject": it["subject"] or "", "title": it["title"][:120],
         "answers": [[a["model"], round(a["cost"], 6), round(a["secs"], 1)] for a in it["answers"]]}
        for it in items]}


def page(items: list[dict], names: dict[str, str]) -> str:
    """Страница голосования: ответы без имён моделей, длинные — свёрнуты;
    выбор уходит на сервер (POST /aitest/pick по той же подписанной ссылке,
    в браузере — запасная копия); имена, победы и цена — по кнопке в конце."""
    from kapibara.core.utils import esc
    blocks = []
    for n, it in enumerate(items):
        answers = "".join(
            f'<div class="a" data-i="{n}" data-j="{j}"><div class="h"><b>Ответ {j + 1}</b>'
            f'<button onclick="vote({n},{j})">Лучший</button></div><div class="t">{_answer_html(a["text"])}</div>'
            f'<div class="m"></div></div>' for j, a in enumerate(it["answers"]))
        blocks.append(f'<section><p class="k">{it["kind"]} {n + 1} из {len(items)} · {esc(it["subject"] or "без предмета")}</p>'
                      f'<h2>{esc(it["title"][:400])}</h2>{answers}</section>')
    secret = base64.b64encode(json.dumps(vote_key(items, names)).encode()).decode()
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light dark">
<title>Слепой тест ИИ</title><style>{CSS}</style></head><body><h1>Слепой тест ИИ</h1><p class="lead">В каждом блоке нажми «Лучший» у самого полезного
ответа (ещё раз — снять). Модели скрыты; выбор сохраняется на сервере — можно бросить и вернуться, итог Claude увидит
сам по этой же ссылке. Длинные ответы свёрнуты — «Целиком». В конце — «Показать модели».</p>
{''.join(blocks)}<div class="bar"><button onclick="reveal()">Показать модели</button> <span id="cnt"></span></div><div id="res"></div>
<script>
const S=JSON.parse(atob("{secret}")),Q="/aitest/pick"+location.search;let V={{}},err="";
try{{V=JSON.parse(localStorage.getItem("aitest")||"{{}}")}}catch(e){{}}
function keep(){{try{{localStorage.setItem("aitest",JSON.stringify(V))}}catch(e){{}}}}
function paint(){{document.querySelectorAll(".a").forEach(a=>a.classList.toggle("on",V[a.dataset.i]==+a.dataset.j));
document.getElementById("cnt").textContent="выбрано "+Object.keys(V).length+" из {len(items)}"+err}}
async function send(i,j){{try{{const r=await fetch(Q,{{method:"POST",headers:{{"Content-Type":"application/json"}},
body:JSON.stringify({{i,j}})}});if(!r.ok)throw 0;V=(await r.json()).picks;err="";keep()}}catch(e){{err=" · не сохранилось на сервере, проверь сеть"}}paint()}}
function vote(i,j){{const off=V[i]===j;if(off)delete V[i];else V[i]=j;keep();paint();send(i,off?-1:j);
if(!off){{const s=document.querySelectorAll("section")[i+1];if(s)setTimeout(()=>s.scrollIntoView({{behavior:"smooth"}}),250)}}}}
function reveal(){{const w={{}},c={{}},t={{}};for(const m in S.names){{w[m]=0;c[m]=0;t[m]=0}}
S.blocks.forEach((b,i)=>b.answers.forEach((a,j)=>{{c[a[0]]+=a[1];t[a[0]]+=a[2];if(V[i]===j)w[a[0]]++}}));
document.querySelectorAll(".a").forEach(a=>{{const r=S.blocks[a.dataset.i].answers[a.dataset.j];
a.querySelector(".m").textContent=S.names[r[0]]+" · $"+r[1].toFixed(5)+" · "+r[2]+" с"}});
document.getElementById("res").textContent=Object.keys(S.names).sort((x,y)=>w[y]-w[x]).map(m=>
S.names[m]+": побед "+w[m]+", всего $"+c[m].toFixed(4)+", в среднем "+(t[m]/S.blocks.length).toFixed(1)+" с").join("\\n")}}
document.querySelectorAll(".t").forEach(t=>{{if(t.scrollHeight>420){{t.classList.add("cut");const b=document.createElement("button");
b.className="more";b.textContent="Целиком";b.onclick=()=>{{t.classList.remove("cut");b.remove()}};t.after(b)}}}});
fetch(Q).then(r=>r.ok?r.json():null).then(d=>{{if(d){{V=d.picks;keep();paint()}}}}).catch(()=>{{}});
paint();
</script></body></html>"""


def tally(key: dict, picks: dict[str, int]) -> str:
    """Итог слепого теста текстом — для Claude по той же ссылке (&view=result)."""
    names, blocks = key.get("names", {}), key.get("blocks", [])
    wins: dict[str, Counter[str]] = {m: Counter() for m in names}
    cost: Counter[str] = Counter()
    secs: Counter[str] = Counter()
    lines = []
    for i, b in enumerate(blocks):
        for model, c, t in b["answers"]:
            cost[model] += c
            secs[model] += t
        j = picks.get(str(i))
        winner = b["answers"][j][0] if j is not None and j < len(b["answers"]) else None
        if winner in wins:
            wins[winner][b["kind"]] += 1
        lines.append(f"{i + 1}. {b['kind']} · {b['subject'] or 'без предмета'} · {b['title'][:80]} → "
                     + (names.get(winner, winner) if winner else "не выбран"))
    order = sorted(names, key=lambda m: -sum(wins[m].values()))
    kinds = sorted({b["kind"] for b in blocks})
    head = [f"Слепой тест: выбрано {len(picks)} из {len(blocks)}.", ""]
    for m in order:
        by_kind = ", ".join(f"{k.lower()} {wins[m][k]}" for k in kinds)
        avg = secs[m] / len(blocks) if blocks else 0
        head.append(f"{names[m]} ({m}): побед {sum(wins[m].values())} ({by_kind}), "
                    f"всего ${cost[m]:.4f}, в среднем {avg:.1f} с")
    return "\n".join(head + ["", "По блокам:"] + lines) + "\n"


async def vote_picks() -> dict[str, int]:
    from database import get_setting
    try:
        return json.loads(await get_setting(VOTE_PICKS) or "{}")
    except ValueError:
        return {}


async def _key() -> dict:
    from database import get_setting
    try:
        return json.loads(await get_setting(VOTE_KEY) or "{}")
    except ValueError:
        return {}


async def vote_pick(i: int, j: int) -> dict[str, int] | None:
    """Выбор в блоке i: ответ j, -1 — снять. None — нет такого блока/ответа."""
    from kapibara.core import locks
    from database import set_setting
    async with locks.lock("aitest", "picks"):
        blocks = (await _key()).get("blocks", [])
        if not 0 <= i < len(blocks) or not -1 <= j < len(blocks[i]["answers"]):
            return None
        current = await vote_picks()
        if j < 0:
            current.pop(str(i), None)
        else:
            current[str(i)] = j
        await set_setting(VOTE_PICKS, json.dumps(current))
        return current


async def vote_result() -> str:
    return tally(await _key(), await vote_picks())


async def save(html: str, kind: str = "vote", key: dict | None = None) -> None:
    """Новая страница; у голосования — и его ключ, прошлый выбор обнуляется."""
    from database import set_setting
    await set_setting(SETTINGS[kind], html)
    if kind == "vote":
        await set_setting(VOTE_KEY, json.dumps(key or {}))
        await set_setting(VOTE_PICKS, "{}")


async def load(kind: str = "vote") -> str | None:
    from database import get_setting
    return await get_setting(SETTINGS[kind])
