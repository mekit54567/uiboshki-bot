# Капибара — своё приложение (Flutter)

Этап 3 дорожной карты (PLAN.md, «Своё приложение»): настоящее приложение для
Android и iPhone, не обёртка над WebApp. Данные — только через API бота
`/api/v1/…` (тот же контракт, что у PWA, `tests/api_contract.json`), вход —
через бота: код → «Да, это я» в Telegram → токен сессии устройства.

- `lib/theme/tokens.dart` — **генерируется** из `design/tokens.json`
  (`python tools/tokens.py`), руками не править.
- `lib/theme/app_theme.dart` — палитры «Глубина» (тёмная) и «Тетрадь»
  (светлая) по теме телефона, шрифт — настройка: «Книжный» (Source Serif 4)
  или «Строгий» (Onest), шрифты в `assets/fonts` (OFL).
- `lib/screens/` — Сегодня, Неделя (повестка с полосой дней), Сдать, Учёба,
  Ещё, вход; `lib/widgets/capsule_tabbar.dart` — меню-капсула.
- Вкладка из ссылки пуша: `?tab=today|week|deadlines|sdo|more`.

```sh
flutter pub get
flutter analyze && flutter test        # тесты — на ответах стенда сайта (site/demo.json)
flutter run --dart-define=API=https://www.uiboshki.ru
```

Стенд в браузере: `flutter build web --dart-define=API= --dart-define=NOW=2026-10-08T10:07:00+03:00`
и отдать `build/web` вместе с ответами `/api/v1/*` из `webapp/static/site/demo.json`.
