#!/bin/sh
# Запуск бота в контейнере (Dockerfile). XRAY_CONFIG задан — сначала Xray,
# и бот ходит за границу через него (OUT_PROXY, если не задан свой).
set -e
mkdir -p "$(dirname "${DATABASE_PATH:-/data/mirea_bot.db}")"
if [ -n "$XRAY_CONFIG" ] && python tools/xray_conf.py /tmp/xray.json; then
    xray run -c /tmp/xray.json &
    export OUT_PROXY="${OUT_PROXY:-http://127.0.0.1:10809}"
    # Xray поднимается за доли секунды; ждём порт, чтобы первый запрос к Telegram не упал
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        python -c "import socket; socket.create_connection(('127.0.0.1', 10809), 1)" 2>/dev/null && break
        sleep 0.5
    done
fi
exec python bot.py
