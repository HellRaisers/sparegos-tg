#!/usr/bin/env bash
# sparegos-tg — ОДНОРАЗОВАЯ настройка на VPS.
# Делает: клон ветки (если нужно), .env из примера, папку data, cron-автодеплой.
# После этого правки прилетают сами: достаточно git push в ветку.
set -e
REPO_DIR="${REPO_DIR:-/opt/sparegos-tg}"
BRANCH="${DEPLOY_BRANCH:-claude/nifty-pasteur-7dGD1}"
REPO_URL="${REPO_URL:-https://github.com/hellraisers/sparegos-tg.git}"

if [ ! -d "$REPO_DIR/.git" ]; then
  echo "▸ Клонирую $BRANCH → $REPO_DIR"
  git clone -b "$BRANCH" "$REPO_URL" "$REPO_DIR"
fi
cd "$REPO_DIR"
git config credential.helper store   # запомнить токен из URL/первого ввода для авто-fetch

[ -f .env ] || { cp .env.example .env; echo "▸ Создан .env — впиши TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID"; }
mkdir -p data
chmod +x deploy/autodeploy.sh

# cron автодеплоя (раз в минуту), без дублей
LINE="* * * * * REPO_DIR=$REPO_DIR DEPLOY_BRANCH=$BRANCH bash $REPO_DIR/deploy/autodeploy.sh"
( crontab -l 2>/dev/null | grep -v "deploy/autodeploy.sh" ; echo "$LINE" ) | crontab -
echo "▸ Cron автодеплоя установлен."

echo ""
echo "✅ Базовая настройка готова. Осталось (один раз):"
echo "   1) nano $REPO_DIR/.env            — токен бота и chat_id"
echo "   2) cp credentials.json $REPO_DIR/data/   — OAuth-файл из Google Cloud"
echo "   3) cd $REPO_DIR && python3 main.py --auth  — подтвердить Google в браузере (создаст data/token.json)"
echo "   4) cd $REPO_DIR && docker compose up -d    — старт"
echo ""
echo "Дальше деплой автоматический: git push в $BRANCH → VPS подхватит за ~1 мин."
