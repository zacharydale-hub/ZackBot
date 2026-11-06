# ZackBot

A humorous, engineering-minded, snarky, and *needlessly skeptical* stand-in for Zack, built for FloVision coworkers to DM on Slack.

Runs on Claude (`claude-opus-5-5`) through the Anthropic Python SDK, with Slack Bolt in Socket Mode, so you don't need a public URL or a server with open ports.

## Layout

```
ZackBot/
├── persona/
│   ├── system_prompt.md   # personality, tone, guardrails
│   └── about_zack.md      # facts about you (fill this in!)
├── zackbot/
│   ├── brain.py           # Claude calls + per-conversation memory
│   ├── cli.py             # terminal chat for tuning the persona
│   └── slack_app.py       # Slack DM + @mention handler
├── slack_manifest.yaml    # one-paste Slack app config
├── requirements.txt
└── .env.example
```

## 1. Local setup

```bash
cd ZackBot
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Put your `ANTHROPIC_API_KEY` in `.env` (or skip it if you've run `ant auth login`).

## 2. Tune the persona in the terminal

```bash
python -m zackbot.cli
```

Edit `persona/about_zack.md` and `persona/system_prompt.md`, then type `/reload` in the CLI to pick up changes. `/reset` wipes the conversation.

## 3. Slack setup

1. Go to https://api.slack.com/apps → **Create New App** → **From a manifest**, pick the FloVision workspace, paste `slack_manifest.yaml`.
2. **Install to Workspace** (may need a workspace admin to approve). Copy the **Bot User OAuth Token** (`xoxb-...`) into `SLACK_BOT_TOKEN`.
3. **Basic Information → App-Level Tokens → Generate**, scope `connections:write`. Copy the `xapp-...` token into `SLACK_APP_TOKEN`.
4. Run it:

   ```bash
   python -m zackbot.slack_app
   ```

5. DM ZackBot in Slack, or `@ZackBot` it in a channel it's been invited to. Saying `reset` wipes its memory of that conversation.

## Quirks

The dice and the cooldowns live in code ([zackbot/quirks.py](zackbot/quirks.py)), not in the prompt, because models are bad at "do this 7% of the time" and at counting. Each user message gets a hidden turn-scoped system note telling Claude what's in play for that reply. Claude reports callouts back with a `[[zb:callout=...]]` marker, which gets stripped before posting.

| Quirk | Trigger | Tunable |
|---|---|---|
| Passion overflow (excited overshare) | Passion topics (prompt) + random | `RANDOM_RAMBLE_P = 0.07` |
| Unsolicited conspiracy theory (claim, "evidence", debunk, move on) | Random, if anything loosely fits | `CONSPIRACY_P = 0.12` |
| Obviously-guessed side "fact" | Random; admits "read it in a thread" / "pulled it out of my butt" when called out | `GUESSED_FACT_P = 0.10` |
| Called out for rambling, contrite | Default reaction; then concise mode | `CONCISE_COOLDOWN = (2, 5)` |
| Called out for rambling, sarcastic | Mock-ChatGPT padded "summary" for 1-2 replies, then concise mode | `SARCASTIC_CALLOUT_P = 0.40` |
| Cheek beat (extra sarcastic reply) | Every 5-10 messages | `CHEEK_EVERY = (5, 10)` |

While in concise mode, rambles, conspiracies and guessed facts are all off. Guessed "facts" are kept to side tangents: never in the real answer, never about named people or customers. Conspiracy theories stick to harmless ones (no health, election, or group-targeting ones).

To watch the quirk engine work: the Slack app always logs each turn's plan, and the CLI does too when `ZACKBOT_DEBUG=1` is set.

Run the offline tests (no API calls):

```bash
.venv\Scripts\python -m unittest discover -s tests -t .
```

## How it behaves

- **DMs**: one rolling conversation per DM (or per thread, if you reply in a thread).
- **@mentions**: one conversation per channel thread; it always replies in-thread.
- Memory is **in-process only**, so a restart forgets everything. Conversations auto-reset after `ZACKBOT_MAX_TURNS` user messages. History is append-only (not trimmed), which the current models require for their thinking blocks.
- **Research:** Claude's server-side web search is on (up to 5 searches per reply). Set `ZACKBOT_WEB_SEARCH=0` to turn it off. Searches are billed separately from tokens.
- If Claude refuses, the API tries a fallback model server-side (`fallbacks: "default"`). If that also declines, ZackBot posts a canned snarky "no".
- Guardrails in the system prompt: no punching down, no commitments made on Zack's behalf, no made-up facts about people/projects, drops the bit if someone's genuinely upset.

## Hosting (later)

Socket Mode only needs outbound internet, so any always-on box works: a small VM, a container, or a spare machine. Things worth adding when it's more than a toy:

- Persist conversations (SQLite/Redis) so restarts don't wipe memory
- Per-user rate limits / a monthly spend cap
- More tools (e.g. Notion or Slack search) so it can look up FloVision stuff, skeptically
