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

## How it behaves

- **DMs**: one rolling conversation per DM (or per thread, if you reply in a thread).
- **@mentions**: one conversation per channel thread; it always replies in-thread.
- Memory is **in-process only**, so a restart forgets everything. Conversations auto-reset after `ZACKBOT_MAX_TURNS` user messages. History is append-only (not trimmed), which the current models require for their thinking blocks.
- If Claude refuses, the API tries a fallback model server-side (`fallbacks: "default"`). If that also declines, ZackBot posts a canned snarky "no".
- Guardrails in the system prompt: no punching down, no commitments made on Zack's behalf, no made-up facts about people/projects, drops the bit if someone's genuinely upset.

## Hosting (later)

Socket Mode only needs outbound internet, so any always-on box works: a small VM, a container, or a spare machine. Things worth adding when it's more than a toy:

- Persist conversations (SQLite/Redis) so restarts don't wipe memory
- Per-user rate limits / a monthly spend cap
- Tools (e.g. Notion or Slack search) so it can actually look things up, skeptically
