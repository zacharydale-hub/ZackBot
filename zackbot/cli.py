"""Chat with ZackBot in the terminal. Good for tuning the persona before Slack.

    python -m zackbot.cli
"""

import logging
import os

from dotenv import load_dotenv

load_dotenv()
# ZACKBOT_DEBUG=1 prints each turn's quirk plan
logging.basicConfig(level=logging.INFO if os.getenv("ZACKBOT_DEBUG") == "1" else logging.WARNING)

from zackbot.brain import ZackBrain  # noqa: E402


def main() -> None:
    brain = ZackBrain()
    print("ZackBot (terminal). Commands: /reset, /reload (re-read persona), /quit\n")
    while True:
        try:
            text = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text == "/quit":
            break
        if text == "/reset":
            brain.reset("cli")
            print("(memory wiped)\n")
            continue
        if text == "/reload":
            brain = ZackBrain()
            print("(persona reloaded, history cleared)\n")
            continue
        print(f"\nzackbot> {brain.reply('cli', text)}\n")


if __name__ == "__main__":
    main()
