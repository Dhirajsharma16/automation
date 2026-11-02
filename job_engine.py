import json, os
from datetime import datetime, timezone
from pathlib import Path
import feedparser
from db import connection, execute
SOURCES_FILE = Path(os.getenv('SOURCES_FILE', 'sources.json'))

def discover_jobs():
    if not SOURCES_FILE.exists(): raise RuntimeError(f'Source config not found: {SOURCES_FILE}')
    config = json.loads(SOURCES_FILE.read_text(encoding='utf-8')); added = checked = 0; errors = []
    with connection() as conn:
        for source in config.get('sources', []):
            if not source.get('enabled'): continue
            if source.get('type') != 'rss':
                errors.append(f"Unsupported source type: {source.get('type')}"); continue
            url = source.get('url', '').strip()
            if not url or 'ADD_' in url:
                errors.append(f"Placeholder URL skipped: {source.get('name')}"); continue
            checked += 1
            try:
                feed = feedparser.parse(url)
                if getattr(feed, 'bozo', False) and not feed.entries:
                    errors.append(f"{source.get('name')}: feed parse failed"); continue
                for entry in feed.entries:
                    item_url = entry.get('link', '').strip()
                    if not item_url: continue
                    cur = execute(conn, "INSERT INTO jobs (source,title,url,summary,published,discovered_at,status) VALUES (?,?,?,?,?,?, 'pending') ON CONFLICT(url) DO NOTHING", (source.get('name','Official source'), entry.get('title','Untitled notice').strip()[:500], item_url, entry.get('summary',entry.get('description','')).strip()[:5000], entry.get('published',entry.get('updated',''))[:200], datetime.now(timezone.utc).isoformat()))
                    if cur.rowcount and cur.rowcount > 0: added += 1
            except Exception as exc: errors.append(f"{source.get('name')}: {exc}")
    return {'sources_checked': checked, 'new_items': added, 'errors': errors}

def get_jobs(status=None, limit=100):
    with connection() as conn:
        sql = 'SELECT id,source,title,url,summary,published,discovered_at,status,posted_at FROM jobs'; params=[]
        if status: sql += ' WHERE status = ?'; params.append(status)
        sql += ' ORDER BY id DESC LIMIT ?'; params.append(limit)
        return [dict(row) for row in execute(conn, sql, tuple(params)).fetchall()]

def approve_job(job_id):
    with connection() as conn:
        return execute(conn, "UPDATE jobs SET status='approved' WHERE id=? AND status='pending'", (job_id,)).rowcount > 0

def mark_posted(job_id):
    with connection() as conn:
        execute(conn, "UPDATE jobs SET status='posted', posted_at=? WHERE id=? AND status='approved'", (datetime.now(timezone.utc).isoformat(), job_id))
