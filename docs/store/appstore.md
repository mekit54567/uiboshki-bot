# App Store — что вставить в App Store Connect

Сначала — подпись и первая сборка: [ios-signing.md](ios-signing.md). Потом —
App Store Connect → приложение → вкладка **App Store** → версия `1.0`.

**Правило 3.1.1:** в App Store-карточке, скриншотах и заметках для проверяющих —
**ни слова про цены, «Капибару+», донаты и оплату на сайте**. Приложение на iPhone
само их не показывает (сервер отвечает `hidden` для `X-App: ios`).

## Карточка

| Поле | Что вставить |
|------|--------------|
| **Name** (до 30) | `Капибара — учёба МИРЭА` |
| **Subtitle** (до 30) | `Расписание, дедлайны и баллы` |
| **Primary Category** | Education (Образование) |
| **Secondary Category** | Productivity (Производительность) |
| **Privacy Policy URL** | `https://www.uiboshki.ru/privacy` |
| **Support URL** | `https://t.me/Partykq` |
| **Marketing URL** | `https://www.uiboshki.ru/about` |
| **Copyright** | `2026 Никита …` (твоё имя, как в аккаунте разработчика) |
| **Price** | Free (бесплатно) |
| **Availability** | все страны (или только Россия — как решишь) |

**Keywords** (до 100 знаков, через запятую без пробелов; слова из названия —
«Капибара», «учёба», «МИРЭА» — не повторяем, Apple их уже учитывает):

```
расписание,сдо,дедлайны,брс,баллы,лекции,студент,рту,пары,зачёт,экзамен,вуз,сессия,moodle,дз
```

Если App Store Connect скажет, что длинно, — убирай слова с конца.

**Promotional Text** (до 170, можно менять без проверки):

```
Расписание на сегодня, сроки из СДО и баллы БРС — в одном приложении. Без поиска по сайтам и чатам.
```

**Description** (до 4000):

```
Капибара — неофициальное приложение студентов РТУ МИРЭА для учёбы: расписание, сроки сдачи, баллы и лекции в одном месте. Его делает студент для своей группы и всех, кому пригодится. Приложение не связано с администрацией университета.

СЕГОДНЯ
• Какая пара идёт, сколько до конца, в каком кабинете и корпусе следующая.
• Подсказка, если следующая пара в другом корпусе.

НЕДЕЛЯ
• Расписание твоей группы по неделям — списком или по дням.
• Поиск расписания любого преподавателя, группы или аудитории МИРЭА — даже без входа.

СДАТЬ
• Сроки из СДО (online-edu.mirea.ru) подтягиваются сами, горящие — сверху.
• Свои сроки, ДЗ группы и заметки к парам.
• Сдать работу в СДО прямо из приложения.

УЧЁБА
• Баллы БРС по каждому предмету и сколько не хватает до «3», «4» или «5».
• Цель по предмету: что ещё можно сдать и какие лекции важны.
• Посещения лекций, файлы курсов по предметам и типам.
• Помощник: отвечает по лекциям твоей группы и показывает, на каком слайде это написано. Конспект лекции — по кнопке.

ЕЩЁ
• Уведомления: утреннее расписание, напоминание перед парой, новые задания и баллы.
• Виджет на рабочий стол, темы оформления и иконки.
• Ачивки за то, что пользуешься приложением.

Вход — через Telegram, VK ID, Яндекс ID или Apple. Подключение СДО — по желанию, своим входом; данные СДО видишь только ты.

Если что-то не работает или есть идея — напиши: https://t.me/Partykq
```

**What's New in This Version** (для 1.0):

```
Первая версия Капибары в App Store: расписание, сроки из СДО, баллы БРС, помощник по лекциям, уведомления и виджет.
```

Для следующих версий — коротко, по-человечески, что появилось (без цен и подписки).

## Скриншоты

**iPhone 6.9" Display** — загрузи из `docs/store/screens/appstore/` по порядку:
`1-today.jpg`, `2-week.jpg`, `3-deadlines.jpg`, `4-goal.jpg`, `5-assistant.jpg`,
`6-more.jpg`, по желанию `1-today-dark.jpg`, `2-week-dark.jpg` (до 10 штук).
Размер 1320×2868 — меньшие экраны Apple сделает сам. iPad не нужен: сборка для
App Store — только iPhone.

Иконка берётся из сборки (1024×1024 уже в проекте).

## App Review Information (заметки для проверяющих)

- **Sign-in required** — да. **User name** — `demo`, **Password** — код доступа
  (значение `REVIEW_CODE` с сервера; в эту инструкцию его не пишем).
- **Contact** — твои имя, телефон, почта.
- **Notes** (по-английски — так быстрее проверяют; подставь код вместо `<КОД>`):

```
Kapibara is an unofficial study companion for students of RTU MIREA (Moscow): class schedule, assignment deadlines from the university LMS (Moodle), grades and lecture files.

Demo access: on the login screen tap "Вход по коду доступа" (Sign in with access code) and enter: <КОД>
The demo account shows a sample student week with sample deadlines, grades and files.

Other sign-in options: Telegram, VK ID, Yandex ID and Sign in with Apple. The public schedule of any teacher, group or room is available without an account ("Расписание без входа").

Connecting the university LMS is optional and uses the student's own university session; it is not needed to review the app.

User-generated content (notes, group homework, lesson comments): every item has "Report" and "Hide author"; reports go to the developer, who removes violating content and its author can appeal. Rules: https://www.uiboshki.ru/rules

Account deletion: More (Ещё) → Security (Безопасность) → Delete all my data.

AI assistant (Kapi): before the first question the app shows what is sent and to whom (OpenRouter, Inc. and Google LLC) and asks for consent; nothing is sent without it (guideline 5.1.2(i)).

The app has no in-app purchases and no ads.
```

## Age Rating (анкета возраста)

Отвечай так:

| Вопрос | Ответ |
|--------|-------|
| Parental Controls / Age Assurance | No |
| Unrestricted Web Access | No (в приложении нет свободного браузера, только свои страницы и СДО) |
| User-Generated Content | **Yes** (заметки, ДЗ группы, комментарии под парой) |
| Messaging and Chat | **Yes** («Обсуждение группы» под парой) |
| Advertising | No |
| Насилие, ужасы, нагота, сексуальный контент, ненормативная лексика, наркотики, алкоголь, азартные игры, конкурсы, медицина | None / No во всех пунктах |

Итоговый возраст Apple посчитает сам (скорее всего 13+) — для студентов это не мешает.

## App Privacy (анкета «какие данные собираем»)

Сверено с `legal_texts.py` (согласие и политика) и `privacy.py`. **Tracking — No**
(рекламы и сторонних счётчиков нет, данные ни с чем не склеиваем). У всех пунктов
ниже: **Linked to the user — Yes**, **Used for tracking — No**.

| Тип данных (как в анкете Apple) | Что это у нас | Зачем (Purpose) |
|---|---|---|
| Contact Info → **Name** | имя из Telegram, VK, Яндекса или Apple | App Functionality |
| Identifiers → **User ID** | id в Telegram / VK / Яндексе / от Apple | App Functionality |
| User Content → **Photos or Videos** | фото к вопросу помощнику | App Functionality |
| User Content → **Other User Content** | вопросы к ИИ, личные сроки, заметки, ДЗ группы, комментарии, оценки преподавателей, файлы для сдачи в СДО | App Functionality |
| Usage Data → **Product Interaction** | что и когда открывал, без содержимого (180 дней) | Analytics, App Functionality |
| Other Data → **Other Data Types** | вход в СДО (кука, зашифрована), баллы, посещения, задания; группа и настройки | App Functionality |

Не собираем — отвечать «No»: почта (почту Apple не сохраняем), телефон, адрес,
геопозиция, контакты, здоровье, финансы, история браузера, поиск, данные о сбоях
(сторонних счётчиков нет), аудио, Device ID.

Про покупки: оплата «Капибары+» идёт только на сайте, не в приложении, — в анкете
App Store «Purchases» не отмечаем.

## Перед отправкой — проверить

- [ ] На сервере заданы `APPLE_TEAM_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY` — кнопка
      «Войти через Apple» видна (правило 4.8, см. [ios-signing.md](ios-signing.md), шаг 9).
- [ ] На сервере задан `REVIEW_CODE`, вход по коду работает с телефона.
- [ ] Сборка из TestFlight выбрана в разделе **Build** версии.
- [ ] Политика `https://www.uiboshki.ru/privacy` открывается.

## Риск, о котором стоит знать

В названии — «МИРЭА». Apple иногда отклоняет приложения с чужим названием в имени
(правило 5.2.1 — чужой бренд без разрешения). Мы честно пишем «неофициальное» в
описании. Если всё же откажут — ответить, что это студенческий проект и данные
публичные, или переименовать, например: `Капибара — учёба студента`
(«МИРЭА» тогда — в Keywords и в описании).
