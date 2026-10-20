# Подпись iPhone-приложения для App Store

Сборку делает GitHub (Actions, задача «ios» в «Сборке приложения») на своём Mac.
Тебе нужно один раз завести в Apple четыре вещи и положить их в секреты GitHub.
**Свой Mac не нужен** — сертификат делается через `openssl` на Windows.

Что получится в конце: кнопка **Run workflow** → через ~20 минут сборка сама
появляется в App Store Connect → TestFlight.

## 0. Аккаунт разработчика

- https://developer.apple.com/programs/enroll — «Apple Developer Program»,
  как **физлицо** (Individual). 99 $ в год. Нужен Apple ID с двухфакторной защитой.
- Оплата: Apple не принимает карты российских банков — нужна иностранная карта.
  Если с оплатой не выйдет — RuStore от этого не зависит, его можно выпускать отдельно.
- В App Store продавцом будет написано твоё имя (как в аккаунте).

Дальше всё — на https://developer.apple.com/account → **Certificates, IDs & Profiles**.

## 1. App Group

**Identifiers** → синий **+** → **App Groups** → Continue →
Description `Kapibara`, Identifier `group.ru.uiboshki.app` → Register.

(Через эту группу виджет на рабочем столе берёт данные приложения.)

## 2. Два App ID — приложение и виджет

**Identifiers** → **+** → **App IDs** → **App** → Continue:

1. **Приложение.** Description `Kapibara`, Bundle ID — **Explicit**:
   `ru.uiboshki.app`. Ниже в Capabilities отметь:
   - **App Groups** → Configure → отметь `group.ru.uiboshki.app`;
   - **Sign In with Apple** → оставь «Enable as a primary App ID».

   Continue → Register.
2. **Виджет.** Ещё раз **+** → App IDs → App: Description `Kapibara Widget`,
   Bundle ID — Explicit: `ru.uiboshki.app.KapibaraWidget`. Capabilities:
   - **App Groups** → Configure → `group.ru.uiboshki.app`.

   Continue → Register.

## 3. Сертификат «Apple Distribution» без Mac

Нужен `openssl`. Он уже есть, если стоит **Git для Windows** (https://git-scm.com).
В PowerShell:

```powershell
Set-Alias openssl "C:\Program Files\Git\usr\bin\openssl.exe"
mkdir $HOME\kapibara-apple
cd $HOME\kapibara-apple
```

**3.1. Закрытый ключ и запрос на сертификат** (подставь свою почту от Apple ID и имя латиницей):

```powershell
openssl genrsa -out kapibara-dist.key 2048
openssl req -new -key kapibara-dist.key -out kapibara-dist.csr -subj "/emailAddress=ТВОЯ@ПОЧТА/CN=Nikita Familiya/C=RU"
```

**3.2. Получить сертификат у Apple.** **Certificates** → **+** → **Apple Distribution**
→ Continue → Choose File → `kapibara-dist.csr` → Continue → **Download**. Скачается
`distribution.cer` — положи его в `$HOME\kapibara-apple`.

**3.3. Склеить ключ и сертификат в `.p12`:**

```powershell
openssl x509 -in distribution.cer -inform DER -out distribution.pem -outform PEM
openssl pkcs12 -export -inkey kapibara-dist.key -in distribution.pem -out kapibara-dist.p12 -keypbe PBE-SHA1-3DES -certpbe PBE-SHA1-3DES -macalg sha1
```

Спросит пароль (два раза) — придумай, латиница и цифры. Это **пароль p12**.
(Странные `-keypbe … sha1` — чтобы файл открылся на Mac в GitHub: новый формат
OpenSSL 3 macOS не всегда понимает.)

`kapibara-dist.key` и `kapibara-dist.p12` — секретные. **Скопируй папку во второе
место** (как ключ Android). Сертификат живёт год — потом повторить шаги 3 и 4 и
заменить секреты.

## 4. Два профиля «App Store Connect»

**Profiles** → **+** → в разделе Distribution — **App Store Connect** → Continue:

1. App ID — `ru.uiboshki.app` → Continue → сертификат из шага 3 → Continue →
   Provisioning Profile Name: `Kapibara App Store` → Generate → **Download**.
2. Ещё раз: App ID — `ru.uiboshki.app.KapibaraWidget` → тот же сертификат →
   Name: `Kapibara Widget App Store` → Generate → **Download**.

Скачаются два файла `.mobileprovision` — положи в `$HOME\kapibara-apple`.

> Поменял Capabilities у App ID (шаг 2) — профили нужно пересоздать (Edit → Save →
> Download) и заменить секреты. Сборка сама проверит и подскажет, чего не хватает.

## 5. Ключ App Store Connect API (для загрузки в TestFlight)

https://appstoreconnect.apple.com → **Users and Access** → вкладка **Integrations** →
**App Store Connect API** → **Team Keys** → **+** (при первом разе — «Request Access»):

- Name: `GitHub`, Access: **App Manager** → Generate.
- **Download API Key** — файл `AuthKey_XXXXXXXXXX.p8`. **Скачать можно только один
  раз** — сохрани во второе место.
- На той же странице: **Key ID** (10 знаков, у строки ключа) и **Issuer ID**
  (сверху, длинный, с дефисами).

## 6. Карточка приложения в App Store Connect

Без неё TestFlight не примет сборку. **Apps** → **+** → **New App**:
Platforms — iOS, Name — `Капибара — учёба МИРЭА`, Primary Language — Russian,
Bundle ID — `ru.uiboshki.app`, SKU — `kapibara`, User Access — Full Access → Create.
Тексты для неё — в [appstore.md](appstore.md).

## 7. Секреты в GitHub

Репозиторий → **Settings** → **Secrets and variables** → **Actions** →
**New repository secret**. Файлы превращаем в текст той же командой, что для
Android (кладёт в буфер обмена, ничего не печатает):

```powershell
cd $HOME\kapibara-apple
[Convert]::ToBase64String([IO.File]::ReadAllBytes("$PWD\kapibara-dist.p12")) | Set-Clipboard
```

| Name                     | Что вставить                                                                 |
|--------------------------|------------------------------------------------------------------------------|
| `IOS_DIST_CERT_P12`      | base64 от `kapibara-dist.p12` (команда выше)                                 |
| `IOS_DIST_CERT_PASSWORD` | пароль p12 из шага 3.3                                                       |
| `IOS_PROFILE_APP`        | base64 от профиля `Kapibara_App_Store.mobileprovision` (имя файла — как скачался) |
| `IOS_PROFILE_WIDGET`     | base64 от профиля виджета `Kapibara_Widget_App_Store.mobileprovision`        |
| `ASC_KEY_ID`             | Key ID из шага 5                                                             |
| `ASC_ISSUER_ID`          | Issuer ID из шага 5                                                          |
| `ASC_KEY_P8`             | весь текст файла `.p8`, вместе со строками `BEGIN`/`END`                      |

Для профилей — та же команда, только с именем файла профиля вместо
`kapibara-dist.p12`. Текст `.p8` в буфер:

```powershell
Get-Content -Raw "$HOME\kapibara-apple\AuthKey_XXXXXXXXXX.p8" | Set-Clipboard
```

Номер команды (Team ID) отдельно не нужен — сборка берёт его из профиля.

## 8. Собрать и отправить в TestFlight

GitHub → **Actions** → «Сборка приложения» → **Run workflow**:
- «Версия для магазинов» — `1.0.0` (каждая новая версия в App Store — больше прошлой);
- галочка **«Загрузить iPhone-сборку в TestFlight»**.

Через ~20 минут — в App Store Connect → твоё приложение → **TestFlight** появится
сборка (ещё 5–30 минут «Processing»). Вопрос про шифрование задавать не будет —
ответ уже вшит в приложение (обычный HTTPS, без своего шифрования).
Поставить себе: приложение **TestFlight** на iPhone → войти тем же Apple ID.

Подписанный `.ipa` лежит и в **Artifacts** запуска (`kapibara-<номер>-appstore.ipa`).
На pull request подписи нет никогда — там только проверка, что всё собирается.
Без секретов сборка работает как раньше: IPA без подписи для AltStore.

## 9. На сервере — до отправки на проверку

1. **Вход через Apple обязателен** (правило App Store 4.8: раз есть вход через
   Telegram, VK и Яндекс). Кнопка появляется, когда на сервере есть ключи:
   developer.apple.com → **Keys** → **+** → Name `Kapibara Sign in`, отметь
   **Sign in with Apple** → Configure → Primary App ID `ru.uiboshki.app` → Save →
   Continue → Register → **Download** (.p8, тоже один раз) и запиши **Key ID**.
   Ключ в одну строку (в буфер):

   ```powershell
   (Get-Content "$HOME\kapibara-apple\AuthKey_КЛЮЧ.p8") -join '\n' | Set-Clipboard
   ```

   На сервере — `kap env`, добавить `APPLE_TEAM_ID` (10 знаков, developer.apple.com →
   Membership details), `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY` (вставить из буфера),
   потом `kap restart`.
2. **Код для проверяющих** — `REVIEW_CODE` (от 12 знаков, придумай сам), тоже через
   `kap env` → `kap restart`. Тогда на экране входа появится «Вход по коду доступа»,
   а сам код ты впишешь в поле Notes при отправке (см. [appstore.md](appstore.md)).

## Что где лежит в коде (для ассистента)

- `.github/workflows/app-build.yml`, задача `ios`: секреты → временная связка ключей
  на раннере → проверка профилей → `tools/ios_store_signing.py` → `flutter build ipa`
  → `xcrun altool --upload-app` → ключи стираются.
- `tools/ios_store_signing.py` правит проект только на раннере: ручная подпись
  приложения и виджета своими профилями, права из `Runner/RunnerStore.entitlements`
  (там «Вход через Apple»; в `Runner.entitlements` его нет — AltStore с ним не
  ставит), только iPhone (иначе App Store требует скриншоты iPad).
