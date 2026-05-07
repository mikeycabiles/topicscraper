# Daily AI Brief

A once-a-day summary of AI signal from a curated set of RSS feeds, distilled by Claude Haiku 4.5 into content angles for an AI-systems consulting personal brand and delivered to Telegram. Scheduling runs on GitHub Actions cron.

## Setup

### 1. Create a Telegram bot and get your chat ID

1. In Telegram, open a chat with [@BotFather](https://t.me/BotFather).
2. Send `/newbot` and follow the prompts to name your bot. BotFather replies with a **bot token** — save it; this is `TELEGRAM_BOT_TOKEN`.
3. Open a chat with your new bot and send it any message (e.g. `hi`).
4. In a browser, visit:
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
   Replace `<TOKEN>` with your bot token. Find `"chat":{"id":...}` in the JSON response — that number is `TELEGRAM_CHAT_ID`.

### 2. Push to a private GitHub repo

Create an empty private repo on GitHub, then from this project root:

```bash
git init
git add .
git commit -m "initial: daily ai brief"
git branch -M main
git remote add origin git@github.com:<you>/<repo>.git
git push -u origin main
```

### 3. Add repository secrets

In the GitHub repo, go to **Settings → Secrets and variables → Actions → New repository secret** and add three secrets:

- `ANTHROPIC_API_KEY` — from [console.anthropic.com](https://console.anthropic.com/)
- `TELEGRAM_BOT_TOKEN` — from step 1
- `TELEGRAM_CHAT_ID` — from step 1

### 4. Run it manually to test

Go to the **Actions** tab → **Daily AI Brief** workflow → **Run workflow**. Within a minute or two, the brief should arrive in your Telegram chat. Check the Actions log if it doesn't.

### 5. Scheduling note (UTC + DST)

The cron is `0 11 * * *` — that is **11:00 UTC daily**. GitHub Actions cron is always UTC, so the local delivery time drifts by one hour twice a year when daylight saving time changes. Adjust the cron in `.github/workflows/daily-ai-brief.yml` if you want to lock to a local clock time.

## Customize

- **Sources, model, lookback window, story cap**: edit the `CONFIG` block at the top of `main.py` (`RSS_FEEDS`, `LOOKBACK_HOURS`, `MAX_STORIES`, `MAX_ITEMS_TO_LLM`, `MODEL`).
- **ICP, story filter, brand voice**: those live inside the prompt in `summarize()`. The current build targets a solo marketing consultant ICP with auto-reject and auto-prioritize lists — adjust there if you change audience.
- **Brand voice and output format**: edit the prompt inside `summarize()` in `main.py`. That is where the four content styles, audience description, prioritization order, and per-story output template live.
