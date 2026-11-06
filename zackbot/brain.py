"""ZackBot's brain: persona loading + per-conversation chat with Claude.

Shared by the CLI and the Slack app. Conversations are kept in memory, keyed by
an arbitrary string (Slack channel/thread id, or "cli").
"""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent
PERSONA_DIR = ROOT / "persona"

MODEL = os.getenv("ZACKBOT_MODEL", "claude-opus-5-5")
EFFORT = os.getenv("ZACKBOT_EFFORT", "medium")
MAX_TURNS = int(os.getenv("ZACKBOT_MAX_TURNS", "40"))

REFUSAL_REPLY = (
    "Yeah no, I'm not touching that one. Even I have standards, "
    "and they're suspiciously low. Try something else."
)
ERROR_REPLY = (
    "Something broke. I'd blame the network, but honestly I'm skeptical "
    "it was ever working. Try again in a sec."
)
RESET_NOTE = (
    "_(Conversation got long, so I wiped my memory. Bold of you to assume "
    "I was remembering it properly anyway.)_\n\n"
)


def load_system_prompt() -> str:
    template = (PERSONA_DIR / "system_prompt.md").read_text(encoding="utf-8")
    about_path = PERSONA_DIR / "about_zack.md"
    about = about_path.read_text(encoding="utf-8") if about_path.exists() else ""
    about = re.sub(r"<!--.*?-->", "", about, flags=re.DOTALL).strip()
    return template.replace("{{ABOUT_ZACK}}", about or "(Nothing yet. Be vague.)")


class ZackBrain:
    def __init__(self) -> None:
        self.client = anthropic.Anthropic()
        self.system_prompt = load_system_prompt()
        self._histories: dict[str, list] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._registry_lock = threading.Lock()

    def _lock_for(self, key: str) -> threading.Lock:
        with self._registry_lock:
            return self._locks.setdefault(key, threading.Lock())

    def reset(self, key: str) -> None:
        with self._lock_for(key):
            self._histories.pop(key, None)

    def reply(self, key: str, user_text: str, speaker: str | None = None) -> str:
        """Send one user message in conversation `key` and return ZackBot's reply."""
        content = f"[{speaker}]: {user_text}" if speaker else user_text

        with self._lock_for(key):
            history = self._histories.setdefault(key, [])
            prefix = ""
            # History is append-only (required so thinking blocks stay valid).
            # Instead of trimming old turns, start over once it gets long.
            user_turns = sum(1 for m in history if m["role"] == "user")
            if user_turns >= MAX_TURNS:
                history.clear()
                prefix = RESET_NOTE

            history.append({"role": "user", "content": content})
            try:
                response = self.client.beta.messages.create(
                    model=MODEL,
                    max_tokens=8000,
                    system=self.system_prompt,
                    messages=history,
                    output_config={"effort": EFFORT},
                    cache_control={"type": "ephemeral"},
                    # Server-side refusal fallback: if the model declines,
                    # the API retries on a suitable fallback model.
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks="default",
                )
            except anthropic.RateLimitError:
                history.pop()
                return "I'm being rate limited. Apparently even I have a quota. Try again in a minute."
            except (anthropic.APIStatusError, anthropic.APIConnectionError):
                history.pop()
                return ERROR_REPLY

            if response.stop_reason == "refusal":
                # Drop the unanswered turn so the conversation stays clean.
                history.pop()
                return prefix + REFUSAL_REPLY

            # Append the full content (incl. thinking blocks) unchanged.
            history.append({"role": "assistant", "content": response.content})

            text = "".join(b.text for b in response.content if b.type == "text").strip()
            return prefix + (text or "...I had a thought and then lost it. Suspicious.")
