# Как вносить изменения

## Ветки и pull request'ы

- Каждое изменение — отдельная ветка и pull request в `main`.
- Мерж — обычным merge commit, не squash. Мержит владелец репозитория.
- CI ([`ci.yml`](.github/workflows/ci.yml)) должен быть зелёным до мержа:
  `ruff`, храповик, `pytest`; для `app/` — `flutter test` и робот-проверка.
- PR открывается сразу готовым к ревью, не черновиком.
- Конфликт с `main` — влить `origin/main` обычным merge. Перед тем как
  звать на мерж: `git fetch origin main && git merge-tree --write-tree HEAD origin/main`.
- В PR, который уже ждёт мержа, не пушить: новые правки — новой веткой.
- Шаблон описания — [`.github/pull_request_template.md`](.github/pull_request_template.md).

## Коммиты

- На русском, по делу: что и зачем.
- `git add` — только конкретных файлов, никогда `-A`.
- Без подписей и ссылок на инструменты в коммитах и описаниях PR.

## Тесты

```bash
pip install -r requirements-dev.txt
python -m pytest -q     # без сети
ruff check .
python tools/ratchet.py
cd app && flutter test  # если менялось приложение
```

- На каждый найденный баг — тест, который его ловит.
- Хендлеры бота проверяются через настоящий `Dispatcher.feed_update`.
- Новый путь API — обновить снимок: `python tools/api_snapshot.py`
  (`tests/api_contract.json`; убрать путь нельзя — сломает установленные приложения).

## Храповик

[`tools/ratchet.py`](tools/ratchet.py) ([ADR 0006](docs/adr/0006-ratchet.md))
считает широкие `except`, молчаливые `pass`, циклы импортов, файлы `.py` в
корне, долг Ruff и ошибки mypy. Потолки — в `tools/ratchet.json`.

- Стало больше — CI красный.
- Стало меньше — `python tools/ratchet.py --update` и закоммитить `ratchet.json`.
- Семейство правил Ruff дошло до нуля — перенести его в `select` в `ruff.toml`.
- Фоновые задачи — через `kapibara.core.tasks.spawn`, не голый `asyncio.create_task`.
- Общий код — вниз по слоям ([ADR 0002](docs/adr/0002-layers.md),
  [ADR 0007](docs/adr/0007-no-import-cycles.md)).

## Changelog и версии

- Обычный PR версию не ставит, а кладёт заметку в свой файл
  `changelog.d/next/<ветка>.md`: `python tools/changelog.py note` (пункты из stdin).
- Раз в ~10 PR отдельный релизный PR собирает заметки в версию:
  `python tools/changelog.py release 5.X.Y Имя` → `changelog.d/5.X.Y.md`.
  Номер — `эпоха.фича.фикс`, у версии есть кодовое имя (пул с пояснениями —
  `FIGURES` в `tools/changelog.py`, свободные — `changelog.py figures`).
- CI (`changelog.py pr-check`) не пускает номер версии в обычный PR и релиз,
  который забрал не все заметки. После мержа `changelog.yml` переносит
  записи в [CHANGELOG.md](CHANGELOG.md); руками туда новые записи не добавлять.
- Теги ставит владелец через GitHub → Releases.

## Что ещё держать в голове

- Меняешь README — поправь оба языка (`README.md`, `README.en.md`, тест
  `tests/test_readme.py`).
- Новый способ пользоваться (платформа, вход) — рассказать везде сразу:
  описание бота, `/start`, `/help`, `/app`, «Ещё → Установить» в Mini App,
  сайт `/about`, README, пост в канал (`tests/test_platforms.py`).
- Новый экран приложения — перенести и в PWA на HTML (`webapp/static/app-html`).
- Новый дизайн — по [брендбуку](docs/brandbook.md), только под `AppStyle.fresh` / `Theme.fresh`.
- Секреты — только в переменных окружения сервера, никогда в репозиторий.
