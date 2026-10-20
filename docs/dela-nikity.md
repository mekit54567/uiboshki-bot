# Дела Никиты

Всё, что нужно сделать руками. Перенесено из папки проекта 19.10. Сделал
пункт — ставь `[x]` (или скажи Claude, он отметит). Значения ключей и паролей
в чат не присылай: они вводятся только на сервере (`ssh root@72.56.243.65`,
потом `kap env` и `kap restart`) или в секретах GitHub.

## 0. Сначала (20.10): касса и всё, что ждёт ключей

Порядок, о котором договорились (20.10): касса (раздел 6), разделы 3–4, потом магазины.

- [ ] Подать в Роскомнадзор два уведомления — об обработке данных и о
      передаче за границу. Что писать в каждое поле — `docs/rkn-uvedomlenie.md`.

## 1. RuStore (Android)

Всё с нашей стороны готово: сборка, тексты, скриншоты — `docs/store/rustore.md`.

- [ ] Ключ подписи Android на своём компьютере и три секрета в GitHub —
      пошагово в `docs/store/android-key.md`. Ключ хранить в двух местах:
      потеряешь — обновления в RuStore не выпустить.
- [ ] Аккаунт разработчика RuStore, карточка приложения по `docs/store/rustore.md`.
- [ ] GitHub → Actions → сборка приложения → Run workflow → скачать APK →
      потыкать на телефоне → загрузить в RuStore.

## 2. App Store

Всё с нашей стороны готово: подписанная сборка включится секретами, тексты и
скриншоты — `docs/store/appstore.md`, подпись без Mac — `docs/store/ios-signing.md`.

- [ ] Apple Developer Program ($99 в год, нужна иностранная карта).
- [ ] По `docs/store/ios-signing.md`: App Group, два App ID, сертификат,
      два профиля, ключ API — и 7 секретов в GitHub.
- [ ] Ключ «Sign in with Apple» (developer.apple.com → Keys, файл .p8), на
      сервере `APPLE_TEAM_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY`. Без входа
      через Apple App Store не примет: у нас есть вход через Telegram, VK, Яндекс.
- [ ] `REVIEW_CODE` на сервере, от 12 знаков — демо-вход для проверяющих; этот
      же код вписать в App Store Connect, «Notes for Review».
- [ ] Run workflow с галочкой TestFlight → потыкать на телефоне → карточка в
      App Store Connect по `docs/store/appstore.md` → на проверку. Название с
      «МИРЭА» Apple может не пропустить — запасной вариант там же.
- [x] `PD_FIO`, `PD_INN`, `PD_EMAIL`, `PD_CITY` на сервере.

## 2½. Пуши в приложении

Шифрованные: Google, Apple и RuStore видят только «кашу». Подробно —
`docs/app-push.md`. Без этого приложение работает, просто без уведомлений.

- [ ] Firebase (console.firebase.google.com): проект, Android-приложение
      `ru.uiboshki.app` → файл `google-services.json` в секрет GitHub
      `GOOGLE_SERVICES_JSON`; сервисный аккаунт (Настройки проекта →
      Сервисные аккаунты → «Создать закрытый ключ») → на сервере
      `FCM_SERVICE_ACCOUNT`.
- [ ] RuStore (после аккаунта): консоль → приложение → Push-уведомления →
      `RUSTORE_PROJECT_ID` (и в секрет GitHub, и на сервер) и
      `RUSTORE_SERVICE_TOKEN` на сервер.
- [ ] Apple (после аккаунта): ключ с галочкой APNs → на сервере
      `APNS_KEY_ID`, `APNS_PRIVATE_KEY`; Claude подключит расширение iPhone.

## 3. Мелочи

- [ ] BotFather: имя бота «Капибара МИРЭА» (адрес @UiboshkiBot не менять).
- [ ] Пополнить OpenRouter на 1000 ₽ (на нём работают Ling и «Подумать ещё»).
- [x] `AI_DAILY_LIMIT=0` — на новом сервере его нет.
- [ ] Заявление в Amvera на возврат остатка (проект уже удалён).
- [ ] Удалить Railway (сервис и переменные).
- [x] Кнопка «Написать нам» — `CONTACT_URL` уже стоит (t.me/Partykq).
- [ ] Бот в чате группы: добавь @UiboshkiBot в общий чат группы, если ещё нет
      (тогда «своя группа» = участники чата и работает «Подслушано»).
- [ ] Удалить ветки `art/icon-redraw`, `art/icon-sheets`, `art/reaction-angry`
      (GitHub → Branches).

## 4. Входы и канал

- [ ] Вход через Яндекс: приложение на oauth.yandex.ru, адрес возврата
      `https://www.uiboshki.ru/api/auth/yandex/callback`, на сервере
      `YANDEX_CLIENT_ID` и `YANDEX_CLIENT_SECRET`.
- [x] Открытый канал Капибары — создан 19.10: t.me/kapibara_mirea, бот — админ.
- [ ] На сервере (`kap env`, потом `kap restart`): `LOGIN_CHANNEL=@kapibara_mirea`,
      `CHANNEL_URL=https://t.me/kapibara_mirea`, `CHANNEL_ID=@uiboshki_dev`
      (иначе посты о разработке уйдут в новый канал). После мержа #227 бот
      пришлёт превью первого поста — «В канал».
- [x] BotFather → `/setdescriptionpic` → картинка «Капибара МИРЭА» (19.10);
      превью сайта от ChatGPT — в 5.108.2.

## 5. Сервер и безопасность

- [x] Ключ шифрования входов в СДО (`SDO_CRYPT_PASSPHRASE`).
- [x] Бэкап в S3 — не нужен, копии остаются в Telegram (решение 19.10).

## 6. Деньги (после App Store; на iPhone оплаты нет)

Оплата в коде готова везде, где она разрешена: сайт `/plus` и `/donate`,
бот (кнопкой-ссылкой на сайт), PWA и Android — ведут на сайт; на iPhone её нет
(правило App Store). Не хватает только кассы — без неё везде «оплата скоро».

- [ ] Касса — одна из двух (`kap env`, потом `kap restart`):
      ЮKassa — `YOOKASSA_SHOP_ID` и `YOOKASSA_SECRET_KEY`; или Robokassa —
      `ROBOKASSA_LOGIN`, `ROBOKASSA_PASS1`, `ROBOKASSA_PASS2` (для проверки
      сначала `ROBOKASSA_TEST=1`, потом убрать).
- [ ] В личном кабинете кассы — адрес уведомлений:
      ЮKassa → HTTP-уведомления `https://www.uiboshki.ru/api/billing/yookassa`
      (событие payment.succeeded); Robokassa → Result URL
      `https://www.uiboshki.ru/api/billing/robokassa` (метод POST, MD5),
      Success URL `https://www.uiboshki.ru/plus/done`, Fail URL
      `https://www.uiboshki.ru/plus`.
- [ ] Спросить ЮKassa и Robokassa, можно ли самозанятому принимать
      добровольные платежи «Добровольная поддержка проекта «Капибара»», если
      донат от 50 ₽ открывает роадмап.
- [ ] Ответить Claude, что поправить в экране `/donate` в боте.
- [ ] Цена: сейчас 149 ₽ для первых; полная новым — `/plus stage full`,
      только когда решишь.
- [ ] Слово на рассылку о подписке `/plusnews`, когда будешь готов.

## 7. Проверить и выбрать

- [ ] Тёмные иконки приложения на iOS 18.
- [ ] В боте `/institutes` — пришлёт `institutes.tsv`; проверить институты
      (И → ИИТ, К → ИИИ, Б → ИКБ, Р → ИРИ, У → ИТУ, Э → ИПТИП, Х → ИТХТ),
      ошибки прислать.
- [ ] PWA на HTML: после мержа открыть на телефоне `www.uiboshki.ru/app-html/` и
      сказать «включай» — тогда `/app` станет HTML-версией (откат без выпуска —
      `PWA_ENGINE=flutter` на сервере).
- [ ] Ачивки: какие иконки станут наградами («Космос» или по смыслу), свои
      подписи полароида — по желанию.

## 7½. Выбрать вид (19.10)

- [x] Оценка преподавателя в капибарах: А (19.10).
- [x] Комментарии под парой: А (19.10).

## 8. Пульс МИРЭА

- [ ] Карта корпусов: на компьютере в Claude Code с Claude in Chrome вставить
      промпт `docs/prompts/pulse-map-capture.md`, прислать
      `pulse-map-<дата>.zip` — тогда включится «Карта» (#219).
- [ ] Написать разработчикам Пульса RTU-TC (t.me/rtu_tc) про официальный
      доступ к своим посещениям — без него посещения считаем по баллам СДО.
- [ ] Сфотографировать QR отметки на паре (после релиза): разберёмся, куда он
      ведёт, и попробуем отмечаться из Капибары.
