#!/usr/bin/env bash
# sparegos-tg — автодеплой ветки с GitHub.
# Ставится в cron (раз в минуту). Если в отслеживаемой ветке появился новый коммит —
# подтягивает и пересобирает контейнер. .env и data/ (секреты, token.json, state.json)
# в .gitignore → git reset --hard их не трогает.
set -e
REPO_DIR="${REPO_DIR:-/opt/sparegos-tg}"
BRANCH="${DEPLOY_BRANCH:-claude/nifty-pasteur-7dGD1}"
LOG="$REPO_DIR/deploy/autodeploy.log"
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
cd "$REPO_DIR" || exit 0

git fetch origin "$BRANCH" -q 2>/dev/null || { echo "$(date '+%F %T') fetch failed" >> "$LOG"; exit 0; }
LOCAL=$(git rev-parse HEAD 2>/dev/null || echo none)
REMOTE=$(git rev-parse "origin/$BRANCH" 2>/dev/null || echo none)
if [ "$LOCAL" != "$REMOTE" ] && [ "$REMOTE" != "none" ]; then
  git reset --hard "origin/$BRANCH" -q
  # пересобираем образ и перезапускаем (Dockerfile COPY *.py → нужен --build)
  docker compose up -d --build >> "$LOG" 2>&1 || true
  echo "$(date '+%F %T') deployed ${REMOTE:0:8} (было ${LOCAL:0:8})" >> "$LOG"
fi
