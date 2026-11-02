import os
import requests

def send_job(job):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("Telegram credentials are missing.")
    published = job.get("published") or "See official notification"
    summary = (job.get("summary") or "").strip()
    if len(summary) > 650:
        summary = summary[:647] + "..."
    message = (
        "🚨 GOVERNMENT JOB UPDATE\n\n"
        f"📌 {job['title']}\n"
        f"🏛️ Source: {job['source']}\n"
        f"📅 Published: {published}\n\n"
        + (f"{summary}\n\n" if summary else "")
        + f"🔗 Official notice / source:\n{job['url']}\n\n"
        "Please check the original official notification for eligibility, vacancies, "
        "application dates and fees before applying.\n\n"
        "🌐 TechTis.in | Sarkari Naukari"
    )
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": message, "disable_web_page_preview": False},
        timeout=25
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")
    return data
