# Upwork → Telegram

Бот мгновенно уведомляет в Telegram о новых **сообщениях клиентов** и
**приглашениях** на Upwork.

Для сообщения в чат приходит: **кто написал** и **сам текст сообщения** —
без ссылок и лишних строк. Сообщения известных клиентов вместо общего
заголовка помечаются хештегом проекта — см. «Маршрутизация по клиентам».

Приглашения выделяются отдельно и помечаются хештегом `#инвайт`:

| Письмо | Что в уведомлении | Метка |
|---|---|---|
| `Invitation to Interview for: …` | вакансия, имя клиента, описание, личное сообщение клиента | 🎯 `#инвайт` `#интервью` |
| `Invitation to Apply for: …` | вакансия, описание | 📨 `#инвайт` |

> Виды писем Upwork о сообщениях клиента, бот ловит оба:
> - `… sent you a message` — содержит текст сообщения, он попадает в уведомление;
> - `You received a direct message from a client` — первый контакт/приглашение,
>   текста в письме нет, поэтому уведомление содержит только имя клиента.
>
> Письма-напоминания `You have an unread message from …` намеренно **не**
> ловятся: это повтор уже присланного сообщения, иначе в канал шли бы дубли.
> Если они всё-таки нужны — добавь `"unread message"` в `GMAIL_SUBJECT_QUERY`.

> **TL;DR что нужно от тебя** (всё остальное уже готово в коде):
> 1. В Google Cloud завести OAuth-credentials (тип *Desktop app*) → файл `credentials.json`.
> 2. Один раз пройти авторизацию Google → появится `token.json`.
> 3. `docker compose up -d`.
>
> Telegram уже настроен: бот и супергруппа «Sparegos || Upwork Messages» (`chat_id = -1003839771199`,
> темы: Клиенты `3`, Инвайты `4`, Сообщения `6`)
> прописываются в `.env`. Подробный чеклист — в конце файла.

Как работает:
- раз в N минут (по умолчанию 10) скрипт ищет в почте новые письма
  по фильтру «**отправитель Upwork** + темы про сообщение клиента»;
- достаёт имя клиента и текст сообщения, шлёт в Telegram;
- помнит уже обработанные письма, чтобы не было дублей.

## Почему Gmail API, а не IMAP/Make

Доступ к почте — **только чтение** (scope `gmail.readonly`). Скрипт ничего
не помечает прочитанным, не двигает и не удаляет письма и **не держит
постоянное IMAP-соединение**. Поэтому нативное приложение Почты на iPhone
продолжает работать как обычно (проблема с пропаданием писем уходит).

---

## Настройка (один раз)

### 1. Telegram-бот
1. В Telegram напиши [@BotFather](https://t.me/BotFather) → `/newbot` → получи **токен**.
2. Добавь бота в нужный чат/группу (или просто напиши ему в личку).
3. Узнай **chat_id**: добавь в чат [@userinfobot](https://t.me/userinfobot)
   или [@getidsbot](https://t.me/getidsbot). Для групп id отрицательный
   (например `-1001234567890`).

### 2. Gmail API
1. Открой [Google Cloud Console](https://console.cloud.google.com/) → создай проект.
2. **APIs & Services → Library** → найди **Gmail API** → **Enable**.
3. **APIs & Services → OAuth consent screen** → тип **External** → заполни
   обязательные поля → в разделе **Test users** добавь свой Gmail-адрес.
4. **APIs & Services → Credentials → Create Credentials → OAuth client ID** →
   тип приложения **Desktop app** → скачай JSON, переименуй в
   `credentials.json` и положи в папку проекта.

### 3. Установка
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # затем заполни TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID
```

### 4. Авторизация в Google (один раз, на машине с браузером)
```bash
python main.py --auth
```
Откроется браузер, войди в нужный Gmail и подтверди доступ. Появится файл
`token.json` — дальше он обновляется сам.

---

## Запуск через Docker (рекомендуется)

Ничего, кроме Docker, ставить не нужно.

1. Сложи секреты:
   ```bash
   cp .env.example .env        # вписать TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID
   mkdir -p data
   cp credentials.json data/   # OAuth-файл из Google Cloud
   ```
2. Один раз пройти авторизацию Google (создаст `data/token.json`).
   - **Проще всего** — на ноутбуке с браузером: `python main.py --auth`
     (положив `credentials.json` рядом), затем скопировать получившийся
     `token.json` в `data/` на сервере.
   - **Или прямо через Docker** на машине, где открыт браузер:
     ```bash
     docker compose run --rm -p 8765:8765 \
       -e OAUTH_PORT=8765 -e OAUTH_OPEN_BROWSER=0 \
       upwork-tg python main.py --auth
     ```
     В логе появится ссылка — открой её в браузере, подтверди доступ.
3. Запуск как сервис:
   ```bash
   docker compose up -d        # соберёт образ и запустит в фоне
   docker compose logs -f      # посмотреть, что пересылается
   ```
   Контейнер крутит `python main.py --loop` и сам перезапускается
   (`restart: unless-stopped`). Проверка почты — каждые `POLL_INTERVAL_SECONDS`.

---

## Запуск без Docker

Одна проверка (для теста и для cron):
```bash
python main.py
```

Постоянный режим с циклом каждые 10 минут:
```bash
python main.py --loop
```

### Вариант А: cron (рекомендуется)
Каждые 10 минут, без постоянно висящего процесса:
```cron
*/10 * * * * cd /path/to/sparegos-tg && .venv/bin/python main.py >> bot.log 2>&1
```

### Вариант Б: systemd (постоянный процесс)
`/etc/systemd/system/upwork-tg.service`:
```ini
[Unit]
Description=Upwork to Telegram
After=network-online.target

[Service]
WorkingDirectory=/path/to/sparegos-tg
ExecStart=/path/to/sparegos-tg/.venv/bin/python main.py --loop
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
```
```bash
sudo systemctl enable --now upwork-tg
```

---

## Настройка фильтра

Всё в `.env` (синтаксис — обычный поиск Gmail):

| Переменная | Назначение | Пример |
|---|---|---|
| `GMAIL_SENDER` | отправитель | `upwork.com` |
| `GMAIL_SUBJECT_QUERY` | условие по теме | `subject:("sent you a message" OR "direct message from a client")` |
| `GMAIL_LOOKBACK` | глубина проверки | `2d` |
| `POLL_INTERVAL_SECONDS` | интервал для `--loop` | `600` |

## Разделение по темам

Уведомления делятся на три вида, и каждый можно направить в свою тему
основного чата:

| Тема | Что туда идёт | Переменная |
|---|---|---|
| Клиенты | письма клиентов из `CLIENT_ROUTES` (Peng, Liad, Marc) | `TOPIC_CLIENTS` |
| Инвайты | приглашения `Invitation to Interview` и `Invitation to Apply` | `TOPIC_INVITES` |
| Сообщения | сообщения остальных клиентов | `TOPIC_MESSAGES` |

Что нужно сделать один раз в Telegram:

1. В основном чате: **Управление группой → Темы** — включить. Telegram
   превратит группу в супергруппу; **её `chat_id` при этом меняется**. Бот это
   переживёт: он поймает новый id из ответа Telegram, продолжит слать туда же и
   напишет в лог `[warn] чат … стал супергруппой, новый id …` — этот id нужно
   вписать в `TELEGRAM_CHAT_ID`.
2. Создать три темы (названия любые).
3. Узнать id темы: открыть тему → любое сообщение → «Копировать ссылку».
   В ссылке вида `t.me/c/2451234567/8/15` **id темы — предпоследнее число** (`8`).
4. Вписать `TOPIC_CLIENTS` / `TOPIC_INVITES` / `TOPIC_MESSAGES` в `.env` и
   выполнить `docker compose up -d`.

Копии в рабочие чаты проектов тем не используют — они идут в общую ленту
своего чата.

## Маршрутизация по клиентам

Чтобы ПМ сразу видел, что письмо от клиента и по какому оно проекту, есть
карта `CLIENT_ROUTES` (в `.env`, формат `Имя=Тег[:chat_id]` через `;`):

```
CLIENT_ROUTES=Peng=HillTribe:-1001111111111;Liad=Truedose:-1002222222222
```

- **Имя** ищется в отправителе письма без учёта регистра («Peng L. via Upwork» → совпадёт `Peng`).
- **Тег** заменяет собой заголовок уведомления: `🏷 #HillTribe — клиентское
  сообщение` — хештег кликабелен, по нему удобно фильтровать канал.
- **chat_id** (необязательно) — копия уведомления дополнительно уходит в
  рабочий чат проекта. Бот должен быть **добавлен в этот чат**; id группы можно
  узнать через @getidsbot (он отрицательный; у супергрупп начинается с `-100`).

По умолчанию (без `.env`) зашито `Peng=HillTribe;Liad=Truedose` — то есть
хештеги работают сразу, а рассылку по рабочим чатам включаешь, дописав chat_id.
Сами chat_id держим в `.env` на сервере, а не в репозитории.

Проверить, видит ли бот чат (ничего никуда не отправляя):

```bash
curl -s "https://api.telegram.org/bot<ТОКЕН>/getChat?chat_id=<CHAT_ID>"
```

`"ok": true` — всё готово; `"chat not found"` — бота ещё не добавили в чат
или id неверный. Если рабочий чат недоступен, уведомление всё равно уйдёт в
общий канал, а в логах появится строка `[warn] рабочий чат … недоступен`.

> Проверь, как именно выглядят реальные письма Upwork в твоём ящике
> (точный адрес отправителя и текст темы), и при необходимости подправь
> `GMAIL_SENDER` / `GMAIL_SUBJECT_QUERY`. Самый надёжный способ — открыть
> поиск Gmail, подобрать запрос, который ловит ровно нужные письма, и
> вставить его части в эти переменные.

## Файлы

| Файл | Что внутри |
|---|---|
| `main.py` | точка входа, цикл и форматирование сообщения |
| `gmail_client.py` | авторизация и чтение Gmail (read-only) |
| `email_parser.py` | разбор письма: заголовки и текст из HTML |
| `telegram_client.py` | отправка в Telegram Bot API |
| `state.py` | список обработанных писем (защита от дублей) |
| `config.py` | чтение настроек из `.env` |

## Безопасность

`.env`, `credentials.json`, `token.json`, `state.json`, папка `data/` уже
в `.gitignore` — **никогда не коммить их**, это доступ к твоей почте и боту.

---

## Чеклист: что нужно сделать тебе

Код, Telegram-бот и Docker уже готовы. Осталось три шага — все они касаются
доступа к **твоему** Gmail (за тебя его выдать нельзя):

- [ ] **1. credentials.json.** В [Google Cloud Console](https://console.cloud.google.com/):
  создать проект → включить **Gmail API** → **OAuth consent screen** (External,
  добавить себя в *Test users*) → **Credentials → OAuth client ID → Desktop app**
  → скачать JSON → переименовать в `credentials.json`, положить в `data/`.
- [ ] **2. token.json.** Пройти авторизацию один раз (см. «Запуск через Docker»,
  шаг 2) — войти в нужный Gmail, подтвердить доступ. Файл создастся сам.
- [ ] **3. Запуск.** `docker compose up -d` — и проверить `docker compose logs -f`.

`.env` заполнить так (Telegram уже известен):
```
TELEGRAM_BOT_TOKEN=8328593322:AAEXYyl3XkSkPcJRZANRDOPr-YsGUQ3qou8
TELEGRAM_CHAT_ID=-1003839771199
TOPIC_CLIENTS=3
TOPIC_INVITES=4
TOPIC_MESSAGES=6
```

После первого успешного запуска стоит проверить, что в группу падают именно
нужные письма. Если фильтр ловит лишнее или пропускает — подправь
`GMAIL_SUBJECT_QUERY` / `GMAIL_SENDER` в `.env` под реальные темы писем Upwork.
