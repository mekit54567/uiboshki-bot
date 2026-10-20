# Пуши своего приложения (Android и iPhone) с шифрованием

Третий канал рассылок после Telegram и веб-пуша: `delivery.deliver` →
`app_push.push_user`. По 152-ФЗ содержимое не видно сервисам доставки: Google
(FCM), Apple (APNs) и RuStore получают только токен устройства и шифротекст.

## Как устроено

1. Человек включает «На этом телефоне» в «Ещё → Уведомления»
   (`app/lib/screens/notify.dart`, `app/lib/app_push.dart`). Приложение
   спрашивает разрешение, берёт токен у сервиса доставки и делает **свой
   случайный ключ AES-256**.
2. Ключ остаётся на телефоне (Android — личное хранилище приложения,
   `push/PushNotify.kt`; iPhone — связка ключей с группой приложения,
   `PushKeys` в `AppDelegate.swift`) и уходит на сервер:
   `POST /api/push/app/subscribe {platform, token, key}`. В базе (`app_push`)
   ключ только зашифрованным — тем же секретом, что входы СДО
   (`sdo_accounts.encrypt`, `SDO_CRYPT_KEY`/`SDO_CRYPT_PASSPHRASE`).
3. Сервер шифрует `{"title","body","tab","tag"}` AES-256-GCM и шлёт
   `{"v": 1, "e": base64(nonce 12 | шифротекст | тег 16)}`:
   - Android — data-сообщение без `notification` (FCM HTTP v1 или RuStore
     Push API). Расшифровывает и показывает уведомление приложение само,
     нативно, и когда оно закрыто (`FcmService.kt`, `RuStoreService`).
   - iPhone — APNs с `mutable-content: 1` и заглушкой «Капибара / Новое
     уведомление». Расшифровывает Notification Service Extension
     (`app/ios/KapibaraNotify`). Без расширения видна заглушка.
4. Нажатие открывает вкладку из пуша (`tab`, как `?tab=` у веб-пуша).
5. Мёртвый токен (FCM `UNREGISTERED`, APNs 410/`BadDeviceToken`, RuStore 404)
   сервер удаляет. «Выйти» в приложении — отписка; «Выйти везде» и «Удалить
   мои данные» стирают записи сразу (`privacy.request_erase`).

Почему не плагины `firebase_messaging` и `flutter_rustore_push`: плагин
RuStore отдаёт data-сообщения только в открытое приложение (в закрытом пуш
терялся бы), а Firebase на iPhone не нужен вовсе (там APNs напрямую) — поэтому
приём и расшифровка на Android свои, на Kotlin, а Dart только включает,
выключает и открывает вкладку. Формат проверяют тесты на одном и том же
примере: `tests/test_app_push.py` (сервер) и
`app/android/app/src/test/.../PushCryptoTest.kt` (телефон).

## Что нужно настроить

Нет переменных — канал выключен, тумблера в приложении нет, всё как раньше.

### Сервер (переменные окружения, `kap env`, потом `kap restart`)

| Переменная | Что это | Где взять |
|---|---|---|
| `FCM_SERVICE_ACCOUNT` | JSON сервисного аккаунта Firebase (целиком текстом или в base64) | Firebase Console → проект → ⚙ Настройки проекта → «Сервисные аккаунты» → «Создать закрытый ключ» |
| `RUSTORE_PROJECT_ID` | ID проекта пушей RuStore | RuStore Консоль → приложение → «Push-уведомления» → «Проекты» |
| `RUSTORE_SERVICE_TOKEN` | сервисный токен проекта | там же, «Сервисный токен» |
| `APNS_KEY_ID` | Key ID ключа APNs | developer.apple.com → Certificates, IDs & Profiles → Keys → «+» с галочкой «Apple Push Notifications service» (можно тот же ключ, что для входа через Apple, если включить в нём APNs) |
| `APNS_PRIVATE_KEY` | содержимое файла `.p8` | скачивается один раз при создании ключа |
| `APNS_TEAM_ID` | Team ID (или берётся `APPLE_TEAM_ID`) | developer.apple.com → Membership |
| `APNS_TOPIC` | необязательно, по умолчанию `ru.uiboshki.app` | — |
| `APNS_SANDBOX` | `1` — для сборок из Xcode (development) | — |

APNs — HTTP/2, пакет `h2` в `requirements.txt`. Запросы идут через
`net.client()`: напрямую, если хост не в `PROXY_HOSTS`.

### Сборка Android

- **FCM**: файл `app/android/app/google-services.json` (Firebase Console →
  «Добавить приложение» Android, пакет `ru.uiboshki.app`). Нет файла — сборка
  проходит, пуши через Google выключены. В CI — секрет
  `GOOGLE_SERVICES_JSON` (содержимое файла), `app-build.yml` кладёт его сам.
  Сбор аналитики и автотокен Firebase выключены в манифесте: токен
  появляется, только когда человек включил пуши.
- **RuStore**: переменная `RUSTORE_PROJECT_ID` при сборке (в CI — секрет с
  тем же именем). Без неё SDK RuStore не подключается (`src/norustore` —
  заглушка): их репозиторий `artifactory-external.vkpartner.ru` из облака
  разработки не открылся (404 на всё), и сборка без него не должна падать.
  С ней — `src/rustore` и `ru.rustore.sdk:pushclient:7.2.0`. **Этот вариант
  ещё ни разу не собирался** — первый раз проверить сборку в CI.

### iPhone — что сделать (нужна подпись для App Store)

Сейчас (AltStore) пуши на iPhone не заработают: Apple выдаёт токен только
приложению с правом `aps-environment`, а AltStore с ним не ставит (как и со
входом через Apple). Код готов; когда будет аккаунт разработчика:

1. В `app/ios/Runner/Runner.entitlements` добавить
   `aps-environment` = `production` (для сборок из Xcode — `development` и
   `APNS_SANDBOX=1` на сервере). В App ID `ru.uiboshki.app` на
   developer.apple.com включить Push Notifications.
2. Добавить target расширения **KapibaraNotify** (файлы уже лежат в
   `app/ios/KapibaraNotify/`):
   - **С Mac, в Xcode**: File → New → Target → Notification Service
     Extension, имя `KapibaraNotify`, язык Swift, «Embed in Runner». Xcode
     создаст свою папку — заменить её файлы нашими (`NotificationService.swift`,
     `Info.plist`, `KapibaraNotify.entitlements`). В настройках target:
     Bundle ID `ru.uiboshki.app.KapibaraNotify`, iOS 15.0, Signing &
     Capabilities → App Groups → `group.ru.uiboshki.app`, Code Signing
     Entitlements = `KapibaraNotify/KapibaraNotify.entitlements`, Info.plist =
     `KapibaraNotify/Info.plist`. Build Phases у Runner: «Embed Foundation
     Extensions» стоит выше «Thin Binary» (иначе цикл сборки Flutter).
   - **Без Mac** — правкой `Runner.xcodeproj/project.pbxproj` по образцу
     target `KapibaraWidget` (так он и был добавлен): свой PBXFileReference
     на три файла и на `KapibaraNotify.appex`, PBXGroup, PBXSourcesBuildPhase
     с `NotificationService.swift`, PBXNativeTarget с
     `productType = "com.apple.product-type.app-extension"`,
     PBXContainerItemProxy + PBXTargetDependency, строка в «Embed Foundation
     Extensions» у Runner, XCBuildConfiguration Debug/Release/Profile (как у
     виджета, но `PRODUCT_BUNDLE_IDENTIFIER = ru.uiboshki.app.KapibaraNotify`,
     `INFOPLIST_FILE = KapibaraNotify/Info.plist`, `CODE_SIGN_ENTITLEMENTS =
     KapibaraNotify/KapibaraNotify.entitlements`, `IPHONEOS_DEPLOYMENT_TARGET
     = 15.0`, без `ASSETCATALOG_*` и WidgetKit). Проверка — iOS-сборка в CI
     (`app-build.yml`); туда же — ad-hoc `codesign` для
     `Payload/Runner.app/PlugIns/KapibaraNotify.appex`, как у виджета.
3. На сервере — `APNS_*` (таблица выше).

Ключ расшифровки приложение кладёт в связку ключей с группой
`group.<id приложения>` (AltStore дописывает к id свой Team ID — группа
ищется так же, как у виджета), запасной путь — настройки группы
(`UserDefaults(suiteName:)`). Расширение читает оттуда же (`PushOpen.loadKey`).

## Что написать в политике (тексты правит координатор, `legal_texts.py`)

- Получатели: Google LLC / Google Ireland (Firebase Cloud Messaging), Apple
  Inc. (Apple Push Notification service), ООО «ВК» (RuStore Push) — только
  если человек сам включил уведомления в приложении.
- Что им уходит: токен устройства (случайный идентификатор, который выдал
  сам сервис) и зашифрованный блок с текстом уведомления. Ключ шифрования
  есть только у телефона и у нас; сервис доставки текст, имя, группу и
  расписание не видит. Apple, кроме того, показывает заглушку «Капибара —
  Новое уведомление», если расширение не расшифровало пуш.
- Трансграничная передача (Google, Apple) — только токен и шифротекст, по
  включению пользователем; выключить — тумблер или выход из аккаунта.
- Храним у себя: токен, вид устройства, ключ (зашифрованным) — до
  выключения, выхода, удаления данных или пока сервис не скажет, что токен
  больше не действует.
