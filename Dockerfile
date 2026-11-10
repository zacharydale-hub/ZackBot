FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY zackbot/ zackbot/
COPY persona/ persona/

# Run as a non-root user
RUN useradd --create-home zackbot
USER zackbot

# Secrets (ANTHROPIC_API_KEY, SLACK_BOT_TOKEN, SLACK_APP_TOKEN) come from the
# environment at runtime. Never bake them into the image.
CMD ["python", "-m", "zackbot.slack_app"]
