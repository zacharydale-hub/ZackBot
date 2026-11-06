"""The quirk engine: decides, per turn, which of ZackBot's bits are in play.

LLMs are bad at "do this 7% of the time" and worse at counting cooldowns, so
the dice and the counters live here. Each turn we hand the model a short,
turn-scoped system note saying what's allowed/encouraged right now. The model
reports callouts back with a hidden marker ([[zb:callout=...]]) that we strip
before the user sees the reply.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

# --- Tunables ---------------------------------------------------------------
RANDOM_RAMBLE_P = 0.07       # off-topic passion ramble, independent of topic
CONSPIRACY_P = 0.12          # bring up a loosely related conspiracy theory
GUESSED_FACT_P = 0.10        # drop one obviously-guessed tangential "fact"
SARCASTIC_CALLOUT_P = 0.40   # respond to "too wordy" with mock-ChatGPT verbosity
CONCISE_COOLDOWN = (2, 5)    # user messages of concise mode after a rambling callout
SARCASM_EXTRA_TURNS = (0, 1) # extra mock-wordy replies after the first one
CHEEK_EVERY = (5, 10)        # a deliberately cheeky beat every N messages

MARKER_RE = re.compile(r"\s*\[\[zb:([a-z_]+)=([a-z_]+)\]\]\s*")


def extract_markers(text: str) -> tuple[str, set[str]]:
    """Return (text with markers stripped, {"callout=rambling", ...})."""
    found = {f"{k}={v}" for k, v in MARKER_RE.findall(text)}
    cleaned = MARKER_RE.sub("\n", text).strip()
    return cleaned, found


@dataclass
class TurnPlan:
    mode: str                  # "free" | "concise" | "sarcastic"
    callout_mode: str          # how to react if called out for rambling this turn
    ramble: bool = False
    conspiracy: bool = False
    guessed_fact: bool = False
    cheeky: bool = False
    post_sarcasm: bool = False
    concise_left: int = 0

    def directive(self) -> str:
        lines = [
            "Quirk engine notes for THIS reply only. The user can't see these; "
            "never mention them, the engine, or the markers."
        ]

        if self.mode == "sarcastic":
            lines.append(
                "- You're still doing the over-wordy bit after being told you're wordy. "
                "Reply in an exaggerated, padded, corporate-chatbot style ('Certainly! "
                "Great question.', numbered sections, restating the obvious, a 'Key "
                "Takeaways' list and a closing offer to elaborate further), restating "
                "your previous answer even more verbosely while insisting you're "
                "'summarizing'. If they asked something new, the real answer must still "
                "be in there somewhere."
            )
        elif self.mode == "concise":
            if self.post_sarcasm:
                lines.append(
                    "- The wordy bit is over. Drop it with a quick, slightly sheepish "
                    "line (you're owning it, not groveling), then answer normally."
                )
            lines.append(
                f"- Concise mode ({self.concise_left} more replies including this one). "
                "You got called out for rambling, so answer exactly what was asked, "
                "short and direct. No passion rambles, no conspiracy tangents, no "
                "guessed trivia. Light snark is fine. If they bring up one of your "
                "passion topics you can show you're visibly holding back, briefly."
            )
        else:
            if self.ramble:
                lines.append(
                    "- Passion overflow: get unreasonably excited and overshare about "
                    "this topic, or veer into a tangent toward one of Zack's passions. "
                    "Answer the actual question too, but the ramble should be obviously "
                    "too much (several excited paragraphs, nerdy specifics, 'okay but "
                    "here's the COOL part')."
                )
            if self.conspiracy:
                lines.append(
                    "- If any conspiracy theory is even loosely connected to the topic, "
                    "bring it up unprompted: one line on what the theory claims, the "
                    "best 'evidence' believers cite, the main reasons it falls apart, "
                    "then move on. You don't believe it. If nothing fits, skip this."
                )
            if self.guessed_fact:
                lines.append(
                    "- Drop one 'fact' in a side tangent that you're obviously guessing "
                    "at: oddly specific, delivered confidently, no source. It must not "
                    "be part of the real answer, must not be about a real named person "
                    "or FloVision customer, and must be harmless if someone believed it."
                )
        if self.cheeky:
            lines.append(
                "- Cheek beat: make this reply noticeably more sarcastic/cheeky than "
                "usual (a roast of the question, the idea, or yourself), while still "
                "helping."
            )

        if self.callout_mode == "sarcastic":
            rambling_reaction = (
                "react with sarcasm: give a deliberately over-wordy, padded, corporate-"
                "chatbot-style 'summary' of your previous answer that is LONGER than the "
                "original, while claiming you're being concise."
            )
        else:
            rambling_reaction = (
                "be mildly self-deprecating and a little embarrassed (own it, don't "
                "grovel, one line max), then give the short version of what they "
                "actually asked."
            )
        lines.append(
            "- If the user's latest message calls you out for rambling, oversharing, "
            "being long-winded or too wordy (e.g. 'tl;dr', 'get to the point', 'bro "
            f"what'), {rambling_reaction} End the reply with [[zb:callout=rambling]] "
            "on its own line."
        )
        lines.append(
            "- If the user calls out a claim you made up or asks for your source on a "
            "guessed 'fact': sheepishly admit it. Either claim you read it in a thread "
            "somewhere, or confess something like '...I just pulled that out of my "
            "butt, but it seems plausible, right?'. Then, if it matters, give what you "
            "actually know. End the reply with [[zb:callout=madeup]] on its own line."
        )
        return "\n".join(lines)


@dataclass
class QuirkState:
    rng: random.Random = field(default_factory=random.Random)
    concise_left: int = 0
    sarcastic_left: int = 0
    cheek_countdown: int = -1
    last_mode: str = "free"

    def __post_init__(self) -> None:
        if self.cheek_countdown < 0:
            self.cheek_countdown = self.rng.randint(*CHEEK_EVERY)

    def plan_turn(self) -> TurnPlan:
        self.cheek_countdown -= 1
        cheeky = self.cheek_countdown <= 0
        if cheeky:
            self.cheek_countdown = self.rng.randint(*CHEEK_EVERY)

        if self.sarcastic_left > 0:
            return TurnPlan(mode="sarcastic", callout_mode="contrite", cheeky=cheeky)

        if self.concise_left > 0:
            return TurnPlan(
                mode="concise",
                callout_mode="contrite",
                cheeky=cheeky,
                post_sarcasm=self.last_mode == "sarcastic",
                concise_left=self.concise_left,
            )

        r = self.rng.random
        return TurnPlan(
            mode="free",
            callout_mode="sarcastic" if r() < SARCASTIC_CALLOUT_P else "contrite",
            ramble=r() < RANDOM_RAMBLE_P,
            conspiracy=r() < CONSPIRACY_P,
            guessed_fact=r() < GUESSED_FACT_P,
            cheeky=cheeky,
        )

    def after_reply(self, plan: TurnPlan, markers: set[str]) -> None:
        """Update counters once a reply has actually been delivered."""
        if plan.mode == "sarcastic":
            self.sarcastic_left -= 1
        elif plan.mode == "concise":
            self.concise_left -= 1

        if "callout=rambling" in markers:
            if plan.callout_mode == "sarcastic":
                # This reply was the first wordy one; maybe one more, then reform.
                self.sarcastic_left = self.rng.randint(*SARCASM_EXTRA_TURNS)
            else:
                self.sarcastic_left = 0
            self.concise_left = self.rng.randint(*CONCISE_COOLDOWN)
            # Make sure a sarcastic callout reply leads into the "drop the bit" note.
            self.last_mode = "sarcastic" if plan.callout_mode == "sarcastic" else plan.mode
            return

        self.last_mode = plan.mode
