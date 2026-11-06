"""Offline tests for the quirk engine and brain plumbing (no API calls).

    python -m unittest discover -s tests
"""

import random
import unittest
from types import SimpleNamespace

from zackbot import quirks
from zackbot.brain import ZackBrain
from zackbot.quirks import QuirkState, TurnPlan, extract_markers


def text_block(text):
    return SimpleNamespace(type="text", text=text)


class FakeClient:
    """Mimics client.beta.messages.create; replies from a queue."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        stop, text = self.replies.pop(0)
        return SimpleNamespace(stop_reason=stop, content=[text_block(text)])


class MarkerTests(unittest.TestCase):
    def test_strips_markers(self):
        text, markers = extract_markers("Fine. Short version: yes.\n[[zb:callout=rambling]]")
        self.assertEqual(text, "Fine. Short version: yes.")
        self.assertEqual(markers, {"callout=rambling"})

    def test_no_markers(self):
        self.assertEqual(extract_markers("hello"), ("hello", set()))


class StateMachineTests(unittest.TestCase):
    def test_contrite_callout_gives_2_to_5_concise_turns(self):
        for seed in range(50):
            s = QuirkState(rng=random.Random(seed))
            plan = TurnPlan(mode="free", callout_mode="contrite")
            s.after_reply(plan, {"callout=rambling"})
            concise = 0
            while (p := s.plan_turn()).mode == "concise":
                concise += 1
                s.after_reply(p, set())
            self.assertIn(concise, range(2, 6))
            self.assertEqual(p.mode, "free")

    def test_sarcastic_callout_then_cooldown(self):
        for seed in range(50):
            s = QuirkState(rng=random.Random(seed))
            s.after_reply(TurnPlan(mode="free", callout_mode="sarcastic"), {"callout=rambling"})
            modes = []
            while (p := s.plan_turn()).mode != "free":
                modes.append(p)
                s.after_reply(p, set())
            sarcastic = [m for m in modes if m.mode == "sarcastic"]
            concise = [m for m in modes if m.mode == "concise"]
            # 1-2 wordy replies total = the callout reply + 0-1 extra
            self.assertIn(len(sarcastic), (0, 1))
            self.assertIn(len(concise), range(2, 6))
            self.assertTrue(concise[0].post_sarcasm)
            self.assertFalse(any(m.post_sarcasm for m in concise[1:]))

    def test_no_quirks_or_sarcasm_during_cooldown(self):
        s = QuirkState(rng=random.Random(1))
        s.concise_left = 3
        p = s.plan_turn()
        self.assertEqual(p.mode, "concise")
        self.assertFalse(p.ramble or p.conspiracy or p.guessed_fact)
        self.assertEqual(p.callout_mode, "contrite")
        self.assertIn("Concise mode", p.directive())

    def test_cheek_beat_every_5_to_10(self):
        s = QuirkState(rng=random.Random(7))
        beats = []
        for i in range(200):
            p = s.plan_turn()
            s.after_reply(p, set())
            if p.cheeky:
                beats.append(i)
        gaps = [b - a for a, b in zip(beats, beats[1:])]
        self.assertTrue(gaps and all(5 <= g <= 10 for g in gaps), gaps)

    def test_random_rates_roughly_right(self):
        s = QuirkState(rng=random.Random(42))
        n = 20000
        plans = [s.plan_turn() for _ in range(n)]
        rate = lambda attr: sum(getattr(p, attr) for p in plans) / n  # noqa: E731
        self.assertAlmostEqual(rate("ramble"), quirks.RANDOM_RAMBLE_P, delta=0.01)
        self.assertAlmostEqual(rate("conspiracy"), quirks.CONSPIRACY_P, delta=0.01)
        self.assertAlmostEqual(rate("guessed_fact"), quirks.GUESSED_FACT_P, delta=0.01)


class BrainTests(unittest.TestCase):
    def test_history_append_only_and_markers_hidden(self):
        client = FakeClient([
            ("end_turn", "So rockets are AMAZING because..."),
            ("end_turn", "Okay okay. Short version: yes.\n[[zb:callout=rambling]]"),
            ("end_turn", "Yes."),
        ])
        brain = ZackBrain(client=client, rng=random.Random(0))
        brain.reply("k", "are rockets cool", speaker="Pat")
        out = brain.reply("k", "tl;dr?", speaker="Pat")
        self.assertEqual(out, "Okay okay. Short version: yes.")
        brain.reply("k", "is coffee good", speaker="Pat")

        first, second, third = (c["messages"] for c in client.calls)
        # Each request starts with the previous one verbatim (append-only).
        self.assertEqual(second[: len(first)], first)
        self.assertEqual(third[: len(second)], second)
        self.assertEqual([m["role"] for m in first], ["user", "system"])
        self.assertEqual(first[1]["clear_at"], "next_user_message")
        # After the rambling callout, the next turn is in concise mode.
        self.assertIn("Concise mode", third[-1]["content"])

    def test_refusal_rolls_back_turn(self):
        client = FakeClient([("refusal", ""), ("end_turn", "hi")])
        brain = ZackBrain(client=client, rng=random.Random(0))
        brain.reply("k", "bad thing")
        brain.reply("k", "hello")
        self.assertEqual([m["role"] for m in client.calls[1]["messages"]], ["user", "system"])

    def test_pause_turn_resumes(self):
        client = FakeClient([("pause_turn", "Searching... "), ("end_turn", "found it.")])
        brain = ZackBrain(client=client, rng=random.Random(0))
        self.assertEqual(brain.reply("k", "look this up"), "Searching... found it.")
        self.assertEqual(len(client.calls), 2)


if __name__ == "__main__":
    unittest.main()
