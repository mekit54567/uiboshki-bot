# Образ бота для своего сервера (переезд в Россию, PLAN.md). На Railway
# по-прежнему собирается Nixpacks (railway.toml), этот файл ему не мешает.
# Внутри — бот и Xray: если задан XRAY_CONFIG, бот ходит за границу через
# него (docker/start.sh, tools/xray_conf.py). База и модели — на постоянном
# диске: DATABASE_PATH=/data/mirea_bot.db.
FROM python:3.12-slim

ARG XRAY_VERSION=25.8.3
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl unzip \
 && curl -fsSL -o /tmp/xray.zip "https://github.com/XTLS/Xray-core/releases/download/v${XRAY_VERSION}/Xray-linux-64.zip" \
 && unzip -q /tmp/xray.zip xray -d /usr/local/bin \
 && chmod +x /usr/local/bin/xray \
 && rm /tmp/xray.zip \
 && apt-get purge -y unzip && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PYTHONUNBUFFERED=1 \
    DATABASE_PATH=/data/mirea_bot.db
EXPOSE 8080
CMD ["sh", "docker/start.sh"]
