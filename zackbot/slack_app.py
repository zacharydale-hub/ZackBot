"""ZackBot on Slack (Socket Mode, so no public URL needed).

    python -m zackbot.slack_app

Handles:
  - DMs to the bot (one ongoing conversation per DM, or per thread if you reply in a thread)
  - @ZackBot mentions in channels (one conversation per thread)
Say "reset" (alone) to wipe the bot's memory of the current conversation.
"""

import logging
import os
import random
import re

from dotenv import load_dotenv

load_dotenv()

from slack_bolt import App  # noqa: E402
from slack_bolt.adapter.socket_mode import SocketModeHandler  # noqa: E402

from zackbot.brain import ZackBrain  # noqa: E402
from zackbot.health import start_health_server  # noqa: E402

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("zackbot")

app = App(token=os.environ["SLACK_BOT_TOKEN"])
brain = ZackBrain()
_names: dict[str, str] = {}

THINKING = [
    "_squints suspiciously..._",
    "_reading this with deep skepticism..._",
    "_consulting my doubts..._",
    "_pretending to think about it..._",
]
MENTION_RE = re.compile(r"<@[A-Z0-9]+>\s*")


def display_name(client, user_id: str) -> str:
    if user_id not in _names:
        try:
            profile = client.users_info(user=user_id)["user"]["profile"]
            _names[user_id] = profile.get("display_name") or profile.get("real_name") or user_id
        except Exception:  # noqa: BLE001 - name is cosmetic, never fail on it
            _names[user_id] = user_id
    return _names[user_id]


def respond(client, event, conv_key: str, reply_thread_ts: str | None) -> None:
    text = MENTION_RE.sub("", event.get("text", "")).strip()
    if not text:
        return
    channel = event["channel"]

    if text.lower() in {"reset", "/reset", "forget everything"}:
        brain.reset(conv_key)
        client.chat_postMessage(
            channel=channel, thread_ts=reply_thread_ts,
            text="Memory wiped. I didn't trust it anyway.",
        )
        return

    placeholder = client.chat_postMessage(
        channel=channel, thread_ts=reply_thread_ts, text=random.choice(THINKING)
    )
    answer = brain.reply(conv_key, text, speaker=display_name(client, event["user"]))
    client.chat_update(channel=channel, ts=placeholder["ts"], text=answer)


@app.event("message")
def on_message(event, client):
    # Only plain DMs from humans; ignore edits, bot posts, joins, etc.
    if event.get("channel_type") != "im" or event.get("subtype") or event.get("bot_id"):
        return
    thread_ts = event.get("thread_ts")
    key = f"{event['channel']}:{thread_ts}" if thread_ts else event["channel"]
    respond(client, event, key, reply_thread_ts=thread_ts)


@app.event("app_mention")
def on_mention(event, client):
    thread_ts = event.get("thread_ts") or event["ts"]
    respond(client, event, f"{event['channel']}:{thread_ts}", reply_thread_ts=thread_ts)


def main() -> None:
    if start_health_server():
        log.info("Health endpoint listening on port %s", os.environ["PORT"])
    log.info("ZackBot connecting to Slack (Socket Mode)...")
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()


if __name__ == "__main__":
    main()
