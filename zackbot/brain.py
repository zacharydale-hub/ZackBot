"""ZackBot's brain: persona loading + per-conversation chat with Claude.

Shared by the CLI and the Slack app. Conversations are kept in memory, keyed by
an arbitrary string (Slack channel/thread id, or "cli").

Each user turn is followed by a turn-scoped system message from the quirk
engine (see quirks.py). History is strictly append-only: earlier messages,
including those system notes and Claude's thinking blocks, are sent back
verbatim, which the current models require.
"""

from __future__ import annotations

import logging
import os
import random
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

import anthropic

from zackbot.quirks import QuirkState, extract_markers

log = logging.getLogger("zackbot.brain")

ROOT = Path(__file__).resolve().parent.parent
PERSONA_DIR = ROOT / "persona"

MODEL = os.getenv("ZACKBOT_MODEL", "claude-opus-5-5")
EFFORT = os.getenv("ZACKBOT_EFFORT", "medium")
MAX_TURNS = int(os.getenv("ZACKBOT_MAX_TURNS", "40"))
WEB_SEARCH = os.getenv("ZACKBOT_WEB_SEARCH", "1") == "1"
MAX_CONTINUATIONS = 3

BETAS = [
    "server-side-fallback-2026-07-01",          # refusal -> fallback model
    "mid-conversation-system-clear-at-2026-08-21",  # turn-scoped quirk notes
]
TOOLS = (
    [{"type": "web_search_20260209", "name": "web_search", "max_uses": 5}]
    if WEB_SEARCH else []
)

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


@dataclass
class Conversation:
    quirks: QuirkState
    messages: list = field(default_factory=list)
    user_turns: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)


class ZackBrain:
    def __init__(self, client=None, rng: random.Random | None = None) -> None:
        self.client = client or anthropic.Anthropic()
        self.rng = rng or random.Random()
        self.system_prompt = load_system_prompt()
        self._convos: dict[str, Conversation] = {}
        self._registry_lock = threading.Lock()

    def _convo(self, key: str) -> Conversation:
        with self._registry_lock:
            if key not in self._convos:
                self._convos[key] = Conversation(quirks=QuirkState(rng=self.rng))
            return self._convos[key]

    def reset(self, key: str) -> None:
        with self._registry_lock:
            self._convos.pop(key, None)

    def _call(self, messages: list):
        extra = {"tools": TOOLS} if TOOLS else {}
        return self.client.beta.messages.create(
            **extra,
            model=MODEL,
            max_tokens=8000,
            system=self.system_prompt,
            messages=messages,
            output_config={"effort": EFFORT},
            cache_control={"type": "ephemeral"},
            betas=BETAS,
            fallbacks="default",
        )

    def reply(self, key: str, user_text: str, speaker: str | None = None) -> str:
        """Send one user message in conversation `key` and return ZackBot's reply."""
        content = f"[{speaker}]: {user_text}" if speaker else user_text
        convo = self._convo(key)

        with convo.lock:
            prefix = ""
            # Never trim old turns (that's a history edit); start over instead.
            if convo.user_turns >= MAX_TURNS:
                convo.messages.clear()
                convo.user_turns = 0
                convo.quirks = QuirkState(rng=self.rng)
                prefix = RESET_NOTE

            plan = convo.quirks.plan_turn()
            log.info("turn plan for %s: %s", key, plan)
            start = len(convo.messages)
            convo.messages.append({"role": "user", "content": content})
            convo.messages.append(
                {"role": "system", "clear_at": "next_user_message", "content": plan.directive()}
            )

            try:
                response = self._call(convo.messages)
                # Web search can pause a long server-side turn; resume it.
                for _ in range(MAX_CONTINUATIONS):
                    if response.stop_reason != "pause_turn":
                        break
                    convo.messages.append({"role": "assistant", "content": response.content})
                    response = self._call(convo.messages)
            except anthropic.RateLimitError:
                del convo.messages[start:]
                return "I'm being rate limited. Apparently even I have a quota. Try again in a minute."
            except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
                log.warning("API error: %s", e)
                del convo.messages[start:]
                return ERROR_REPLY

            if response.stop_reason == "refusal":
                # Drop the unanswered turn (it's the tail, so nothing later depends on it).
                del convo.messages[start:]
                return prefix + REFUSAL_REPLY

            # Append the full content (incl. thinking blocks + markers) unchanged.
            convo.messages.append({"role": "assistant", "content": response.content})
            convo.user_turns += 1

            # Collect text from this turn's assistant messages (more than one if paused).
            raw = "".join(
                b.text
                for m in convo.messages[start:]
                if m["role"] == "assistant"
                for b in m["content"]
                if b.type == "text"
            ).strip()
            text, markers = extract_markers(raw)
            convo.quirks.after_reply(plan, markers)
            if markers:
                log.info("markers for %s: %s", key, markers)
            return prefix + (text or "...I had a thought and then lost it. Suspicious.")
