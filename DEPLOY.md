# Deploying ZackBot

ZackBot uses Slack **Socket Mode**: it opens an outbound connection to Slack and keeps it open. That means:

- **No public URL, no inbound ports.** It only needs outbound HTTPS to `slack.com` and `api.anthropic.com`.
- **It must stay running.** Anything that scales to zero when idle will drop the Slack connection, so ZackBot goes deaf.
- **Run exactly one copy.** Conversation memory lives in the process, so two copies would each remember half of every chat.

Two options below. Pick one.

| | Cloud Run (recommended) | Small VM |
|---|---|---|
| Effort | One deploy command | Manage a Linux box |
| Secrets | Google Secret Manager | `.env` file on the VM |
| Updates | Re-run the deploy command | `git pull` + rebuild |
| Restarts on crash | Automatic | Docker `--restart` |
| Cost | Billed for 1 always-on instance | Billed for the VM |

Check current prices in the Google Cloud pricing calculator before picking; both are small, always-on line items.

## What you need first

- A Google Cloud project with billing, and permission to deploy to it (or someone who does)
- The three secrets: `ANTHROPIC_API_KEY`, `SLACK_BOT_TOKEN` (`xoxb-...`), `SLACK_APP_TOKEN` (`xapp-...`)
- `gcloud` CLI installed and logged in: `gcloud auth login`, then `gcloud config set project PROJECT_ID`

Replace `PROJECT_ID` and `REGION` (e.g. `us-central1`) below.

---

## Option A: Cloud Run

### 1. Enable the APIs (once)

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com
```

### 2. Store the secrets (once)

Run each one, pasting the real value in place of the placeholder:

```bash
printf '%s' "sk-ant-..." | gcloud secrets create zackbot-anthropic-key --data-file=-
```

```bash
printf '%s' "xoxb-..." | gcloud secrets create zackbot-slack-bot-token --data-file=-
```

```bash
printf '%s' "xapp-..." | gcloud secrets create zackbot-slack-app-token --data-file=-
```

To rotate one later, use `gcloud secrets versions add <name> --data-file=-` the same way, then redeploy.

### 3. Create a service account that can read only those secrets (once)

```bash
gcloud iam service-accounts create zackbot-runner --display-name "ZackBot runtime"
```

```bash
for s in zackbot-anthropic-key zackbot-slack-bot-token zackbot-slack-app-token; do gcloud secrets add-iam-policy-binding $s --member="serviceAccount:zackbot-runner@PROJECT_ID.iam.gserviceaccount.com" --role="roles/secretmanager.secretAccessor"; done
```

### 4. Deploy (also how you update)

From the `ZackBot` folder:

```bash
gcloud run deploy zackbot \
  --source . \
  --region REGION \
  --service-account zackbot-runner@PROJECT_ID.iam.gserviceaccount.com \
  --min-instances 1 \
  --max-instances 1 \
  --no-cpu-throttling \
  --memory 512Mi \
  --no-allow-unauthenticated \
  --set-secrets ANTHROPIC_API_KEY=zackbot-anthropic-key:latest,SLACK_BOT_TOKEN=zackbot-slack-bot-token:latest,SLACK_APP_TOKEN=zackbot-slack-app-token:latest
```

Why those flags:

- `--min-instances 1` keeps it running when nobody's chatting.
- `--max-instances 1` keeps it to one copy, so memory isn't split.
- `--no-cpu-throttling` keeps CPU on between HTTP requests. Without it, the Slack connection stalls.
- `--no-allow-unauthenticated` blocks the public from hitting the health URL. Slack doesn't need it.

Cloud Run requires the container to answer HTTP on `$PORT`. ZackBot starts a tiny health endpoint automatically when `PORT` is set ([zackbot/health.py](zackbot/health.py)).

Optional settings go in as env vars, e.g. `--set-env-vars ZACKBOT_EFFORT=medium,ZACKBOT_WEB_SEARCH=1`.

### 5. Check it

```bash
gcloud run services logs read zackbot --region REGION --limit 50
```

Look for `ZackBot connecting to Slack (Socket Mode)...` followed by Bolt's Socket Mode connection messages and no errors. Then DM ZackBot in Slack.

---

## Option B: Small VM with Docker

### 1. Create the VM

A small shared-core machine (e.g. `e2-small`) is plenty. Any Linux image with Docker works; on Debian:

```bash
gcloud compute instances create zackbot --zone REGION-a --machine-type e2-small --image-family debian-12 --image-project debian-cloud
```

```bash
gcloud compute ssh zackbot --zone REGION-a
```

### 2. On the VM: install Docker, get the code, add secrets

```bash
sudo apt-get update && sudo apt-get install -y docker.io git
```

```bash
git clone https://github.com/zacharydale-hub/ZackBot.git && cd ZackBot
```

Create `.env` with the three secrets (same format as `.env.example`), then lock it down:

```bash
chmod 600 .env
```

### 3. Build and run

```bash
sudo docker build -t zackbot . && sudo docker run -d --name zackbot --restart unless-stopped --env-file .env zackbot
```

`--restart unless-stopped` brings it back after crashes and VM reboots.

### Update

```bash
git pull && sudo docker build -t zackbot . && sudo docker rm -f zackbot && sudo docker run -d --name zackbot --restart unless-stopped --env-file .env zackbot
```

### Logs

```bash
sudo docker logs -f zackbot
```

---

## Test the container locally first (optional)

With Docker Desktop and your `.env` filled in:

```bash
docker build -t zackbot . && docker run --rm --env-file .env zackbot
```

Stop it before deploying elsewhere, or two copies will share the Slack traffic.

## Known limits

- **Restarts wipe memory.** Every redeploy, crash, or VM reboot forgets ongoing conversations. Persisting history (Firestore, SQLite on a disk, Redis) is the fix when it matters.
- **No per-user rate limits yet.** Put a monthly spend limit on the Anthropic key.
