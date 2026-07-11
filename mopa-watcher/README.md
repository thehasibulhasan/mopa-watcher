# MOPA Latest News → Telegram (free, runs on GitHub Actions)

Checks `https://mopa.gov.bd/views/latest-news` twice a day — **11:00 AM and
5:00 PM Bangladesh time** — and sends you a Telegram message for every new
entry. Runs entirely on GitHub's free scheduled-workflow service, so there's
nothing to host, pay for, or keep running on your own computer.

---

## Step 1 — Create your Telegram bot (2 minutes)

1. Open Telegram, search for **@BotFather**, and start a chat.
2. Send `/newbot` and follow the prompts (pick a name and a username).
3. BotFather replies with a **token** that looks like:
   `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxx` — copy it, you'll need it soon.
4. Now send your new bot any message, e.g. "hi" (it won't reply — that's fine,
   this just lets it "see" your chat).
5. In your browser, go to (replacing with your real token):
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
6. In the JSON that appears, find `"chat":{"id":` — that number is your
   **chat ID**. Copy it too.

## Step 2 — Create a GitHub repository

1. Go to [github.com](https://github.com) and sign in (or create a free
   account).
2. Click **New repository**. Name it anything, e.g. `mopa-watcher`. It can be
   **Private** — GitHub Actions' free minutes apply either way, and this job
   is tiny (runs a few seconds, twice a day).
3. Click **Create repository**.

## Step 3 — Upload these files to the repo

Upload the files exactly as provided (keep the folder structure — the
workflow file must stay inside `.github/workflows/`):

```
mopa-watcher/
├── check_mopa.py
├── seen_state.json
├── requirements.txt
└── .github/
    └── workflows/
        └── check.yml
```

Easiest way: on your new repo's GitHub page, click **Add file → Upload
files**, drag all four files/folders in, and commit. (Uploading a folder like
`.github/workflows/check.yml` works fine via drag-and-drop in the browser —
GitHub preserves the path.)

## Step 4 — Add your Telegram credentials as secrets

Secrets keep your bot token out of the code (never paste it directly into
`check_mopa.py`).

1. In your repo, go to **Settings → Secrets and variables → Actions**.
2. Click **New repository secret**.
   - Name: `TELEGRAM_BOT_TOKEN` → Value: the token from Step 1.
   - Click **Add secret**.
3. Click **New repository secret** again.
   - Name: `TELEGRAM_CHAT_ID` → Value: the chat ID from Step 1.
   - Click **Add secret**.

## Step 5 — Turn it on / test it

1. Go to the **Actions** tab of your repo.
2. You should see a workflow called **"Check MOPA Latest News"**. If GitHub
   shows a banner asking to enable Actions, click to enable it.
3. Click on the workflow, then click **Run workflow** (the manual trigger
   button) to test it immediately instead of waiting for 11 AM/5 PM.
4. Check the run logs — and check Telegram. On this very first run, the bot
   won't alert you about the ~30 existing news items; it just quietly
   remembers them and sends one confirmation message:
   *"✅ MOPA latest-news watcher is live..."*
5. From then on, it checks automatically at **11:00 AM and 5:00 PM Dhaka
   time every day**, and messages you only for genuinely new entries.

That's it — no server, no bill, nothing to keep running on your machine.

---

## How it works / notes

- The schedule in `check.yml` uses UTC (`0 5 * * *` and `0 11 * * *`), which
  is 11:00 AM and 5:00 PM in Bangladesh (UTC+6) year-round — Bangladesh
  doesn't observe daylight saving, so this never drifts.
- **GitHub's scheduled runs aren't laser-precise** — GitHub says cron jobs
  may fire a few minutes late during high load, but for a twice-daily check
  this doesn't matter.
- After each run, the workflow commits the updated `seen_state.json` back to
  your repo — that's how it remembers what it already notified you about
  between runs (GitHub Actions doesn't have persistent storage between runs
  otherwise).
- If you ever want to reset and get notified about everything currently on
  the page again, just edit `seen_state.json` back to `{"seen": []}`.
- If MOPA changes their website layout, the script's table-parsing logic may
  need a small update — feel free to bring it back here and I can help fix it.
