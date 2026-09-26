"""
Подбор лекций под вопрос. После выгрузки СДО (сотни файлов) текст лекций
одного предмета — это сотни тысяч символов, и отдавать его Gemini целиком
на каждый вопрос в чате медленно и упирается в лимит токенов. Поэтому в
модель идут лекции, в которых есть слова вопроса (сначала совпадения в
названии), в пределах бюджета. Без выбранного предмета — то же по всем
предметам, но только при явном совпадении: на «привет» лекции не нужны.

Ничего не индексируем заранее: слова каждой лекции считаются один раз и
кэшируются, пока текст лекций не поменяется.
"""

import re

SUBJECT_BUDGET = 200_000   # ~60К токенов — отвечает быстро и не упирается в лимиты
AUTO_BUDGET = 60_000       # без выбранного предмета — только самое подходящее
AUTO_MIN_SCORE = 4         # совпадение в названии (3) + в тексте, или 4 слова вопроса в тексте

_WORD = re.compile(r"[а-яёa-z]{4,}|\d{1,3}", re.I)
_STOP = {
    "что", "это", "как", "такое", "почему", "зачем", "когда", "какой", "какая", "какие", "каких", "есть",
    "объясни", "расскажи", "помоги", "реши", "решить", "задача", "задачу", "пожалуйста", "нужно", "надо",
    "можно", "будет", "если", "чтобы", "очень", "тема", "теме", "темы", "лекция", "лекции", "лекцию",
    "этой", "этот", "этого", "этом", "меня", "тебя", "себя", "всех", "всего", "только", "сейчас",
    "сегодня", "завтра", "неделе", "неделю", "недели", "пара", "пары", "сдавать", "сдать", "дедлайн",
}
_cache: dict[tuple, list[tuple]] = {}


def _stems(text: str) -> set[str]:
    out = set()
    for w in _WORD.findall(text.lower().replace("ё", "е")):
        if w in _STOP:
            continue
        out.add(w if w.isdigit() else w[:6])
    return out


def _blocks(context: str) -> list[tuple[str, str, set, set]]:
    """[(заголовок, блок, слова заголовка, слова текста)] — блоки в формате
    database.get_subject_lecture_context: "=== Название ===\\nтекст"."""
    key = (len(context), context[:200], context[-200:])
    if key not in _cache:
        parts = context.split("\n\n=== ")
        blocks = []
        for i, part in enumerate(parts):
            block = part if i == 0 else "=== " + part
            title = block.split("\n", 1)[0].strip("= ").strip()
            blocks.append((title, block, _stems(title), _stems(block)))
        if len(_cache) > 64:
            _cache.clear()
        _cache[key] = blocks
    return _cache[key]


def _score(query: set, title: set, body: set) -> int:
    return 3 * len(query & title) + len(query & body)


def pick(context: str, query: str, budget: int = SUBJECT_BUDGET, min_score: int = 0) -> str:
    """Лекции под вопрос в пределах budget, в исходном порядке. Короткий
    контекст — как есть (при min_score=0). Без слов в вопросе — первые
    лекции по бюджету, как раньше."""
    if not context.strip():
        return ""
    if min_score == 0 and len(context) <= budget:
        return context
    blocks = _blocks(context)
    q = _stems(query or "")
    scored = [(_score(q, t, b), i) for i, (_, _, t, b) in enumerate(blocks)] if q else []
    order = [i for s, i in sorted(scored, key=lambda x: (-x[0], x[1])) if s > 0 and s >= min_score]
    if not order and min_score == 0:
        order = list(range(len(blocks)))      # ничего не совпало — первые лекции, как раньше
    chosen, used = [], 0
    for i in order:
        size = len(blocks[i][1]) + 2
        if used + size > budget:
            if not chosen and min_score == 0:  # даже одна лекция не влезает — её начало
                return blocks[i][1][:budget]
            continue
        chosen.append(i)
        used += size
    return "\n\n".join(blocks[i][1] for i in sorted(chosen))
