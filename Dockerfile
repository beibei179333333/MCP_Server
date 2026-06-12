# 2026 World Cup Telegram bot
FROM python:3.11-slim

WORKDIR /app

COPY worldcup_bot/requirements.txt /app/worldcup_bot/requirements.txt
RUN pip install --no-cache-dir -r worldcup_bot/requirements.txt

COPY worldcup_bot /app/worldcup_bot

# Config comes from environment variables (see .env.example).
# Persist the SQLite DB outside the container with:  -v $(pwd)/data:/app/data
ENV DB_PATH=/app/data/worldcup_bot.db
VOLUME ["/app/data"]

ENTRYPOINT ["python", "-m", "worldcup_bot"]
CMD ["run"]
