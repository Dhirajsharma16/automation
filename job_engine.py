import json
import os
from datetime import datetime, timezone
from pathlib import Path

import feedparser
from db import connection, execute

SOURCES_FILE = Path(os.getenv("SOURCES_FILE", "sources.json"))

def discover_jobs():
    if not SOURCES_FILE.exists():
        raise RuntimeError(f"Source config not found: {SOURCES_FILE}")
    config = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    added = 0
    checked = 0
    errors = []

    with connection() as conn:
        for source in config.get("sources", []):
            if not source.get("enabled"):
                continue
            if source.get("type") != "rss":
                errors.append(f"Unsupported source type: {source.get('type')}")
                continue
            feed_url = source.get("url", "").strip()
            if not feed_url or "ADD_" in feed_url:
                errors.append(f"Placeholder URL skipped: {source.get('name')}")
                continue
            checked += 1
            try:
                feed = feedparser.parse(feed_url)
                if getattr(feed, "bozo", False) and not feed.entries:
                    errors.append(f"{source.get('name')}: feed parse failed")
                    continue
                for entry in feed.entries:
                    item_url = entry.get("link", "").strip()
                    if not item_url:
                        continue
                    cur = execute(conn, """
                        INSERT INTO jobs
                        (source, title, url, summary, published, discovered_at, status)
                        VALUES (?, ?, ?, ?, ?, ?, 'pending')
                        ON CONFLICT(url) DO NOTHING
                    """, (
                        source.get("name", "Official source"),
                        entry.get("title", "Untitled recruitment notice").strip()[:500],
                        item_url,
                        entry.get("summary", entry.get("description", "")).strip()[:5000],
                        entry.get("published", entry.get("updated", ""))[:200],
                        datetime.now(timezone.utc).isoformat()
                    ))
                    if cur.rowcount == 1:
                        added += 1
            except Exception as exc:
                errors.append(f"{source.get('name')}: feed request failed: {exc}")
    return {"sources_checked": checked, "new_items": added, "errors": errors}

def get_jobs(status=None, limit=100):
    with connection() as conn:
        sql = """SELECT id, source, title, url, summary, published, discovered_at, status, posted_at
                 FROM jobs"""
        params = ()
        if status:
            sql += " WHERE status = ?"
            params = (status,)
        sql += " ORDER BY id DESC LIMIT ?"
        cur = execute(conn, sql, params + (limit,))
        return [dict(row) for row in cur.fetchall()]

def approve_job(job_id):
    with connection() as conn:
        cur = execute(conn, "UPDATE jobs SET status='approved' WHERE id=? AND status='pending'", (job_id,))
        return cur.rowcount > 0

def mark_posted(job_id):
    with connection() as conn:
        execute(conn, "UPDATE jobs SET status='posted', posted_at=? WHERE id=? AND status='approved'",
                (datetime.now(timezone.utc).isoformat(), job_id))
