# TechTis Job Intelligence Engine — Free-first v2

A small Python service for discovering recruitment updates from configured RSS/Atom feeds, saving them in Supabase Postgres, and publishing only manually approved jobs to Telegram.

## Architecture for a ₹0 starting budget

- Render Free Web Service hosts the Python API. Free services sleep after inactivity and may take about a minute to wake.
- cron-job.org Free sends an authenticated HTTP POST to `/run` every 3 hours.
- Supabase Free Postgres stores jobs and deduplication state.
- Telegram Bot API publishes approved alerts.

This is a prototype, not an uptime guarantee. Render's dedicated Cron Jobs may be paid, so this design uses cron-job.org.

## Implemented

- Authenticated `/run` endpoint for scheduled discovery
- RSS/Atom feed ingestion and URL-based duplicate detection
- Supabase Postgres persistence, with SQLite fallback for local testing
- Admin endpoint to list pending jobs
- Manual approval and Telegram publishing
- Health endpoint and Render deployment blueprint

## Not yet implemented

- No all-India web crawler is included. Only feeds configured in `sources.json` are checked.
- Many recruitment bodies do not publish RSS feeds. Official-site adapters must be developed and tested individually.
- Human verification against the original official notification is required before approval.
- Instagram, YouTube, LinkedIn and X publishing are not included in this Telegram-first version.

## 1. Local setup (Windows)

Install Python 3.11+ and Git. Extract the project, open the folder in VS Code, then:

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python app.py
```

Open `http://127.0.0.1:10000/health`.

## 2. Supabase database

Open Supabase SQL Editor and run all SQL from `supabase_schema.sql`. Copy the server-side Postgres connection string from Project Settings → Database and store it as Render's `DATABASE_URL`.

Never put database credentials in GitHub or browser code.

## 3. Telegram bot

1. Create a bot using `@BotFather`.
2. Add it as an administrator of your Sarkari Naukari channel with permission to post.
3. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in Render environment variables.

For a public channel, the chat ID can be `@YourChannelUsername`.

## 4. Deploy to Render

1. Create a private GitHub repository and upload this project.
2. In Render choose New → Web Service and connect the repository.
3. Build command: `pip install -r requirements.txt`.
4. Start command: `gunicorn app:app`.
5. Select the Free instance.
6. Add environment variables: `DATABASE_URL`, `AUTOMATION_SECRET`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, and `SOURCES_FILE=sources.json`.
7. Deploy. Keep secrets in Render only.

## 5. cron-job.org (every 3 hours)

Create a job with:
- URL: `https://YOUR-RENDER-SERVICE.onrender.com/run`
- Method: `POST`
- Header: `X-Automation-Secret: YOUR_AUTOMATION_SECRET`
- Schedule: every 3 hours

The first request after Render sleeps may take around a minute.

## 6. Configure official sources

Edit `sources.json`. Add only real RSS/Atom feed URLs verified to belong to official recruitment bodies, then set `enabled` to `true`. The included URL is a disabled placeholder, not a real feed.

## 7. Review and publish

All discovered jobs remain pending. They are not published automatically.

- `GET /admin/jobs` lists the queue.
- `POST /admin/approve/JOB_ID` approves a job after checking its official notice.
- `POST /admin/publish` publishes approved jobs to Telegram.

All admin requests require the `X-Automation-Secret` header.

## Security

- Keep the repository private.
- Store tokens and passwords only in Render environment settings.
- Use a long random `AUTOMATION_SECRET`.
- Rotate any token that has been exposed.
- Never publish unverified job details.
