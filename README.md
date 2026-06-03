# Upwork → Telegram

Бот пересылает в Telegram-чат содержимое писем от Upwork об уведомлении
о новых сообщениях клиентов.

Как работает:
- раз в N минут (по умолчанию 10) скрипт ищет в почте новые письма
  по фильтру «**отправитель Upwork** + **тема про новое сообщение**»;
- достаёт текст письма и шлёт его в Telegram через бота;
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

## Запуск

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
| `GMAIL_SUBJECT_QUERY` | условие по теме | `subject:("new message" OR "новое сообщение")` |
| `GMAIL_LOOKBACK` | глубина проверки | `2d` |
| `POLL_INTERVAL_SECONDS` | интервал для `--loop` | `600` |

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

`.env`, `credentials.json`, `token.json`, `state.json` уже в `.gitignore` —
**никогда не коммить их**, это доступ к твоей почте и боту.
