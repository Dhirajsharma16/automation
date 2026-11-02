import json, os
from datetime import datetime, timezone
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
import feedparser
import requests
from db import connection, execute

SOURCES_FILE = Path(os.getenv('SOURCES_FILE', 'sources.json'))
KEYWORDS = ('recruitment', 'vacancy', 'vacancies', 'notification', 'advertisement',
            'career', 'careers', 'apply online', 'employment', 'job', 'selection',
            'direct recruitment', 'corrigendum')

class NoticeLinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            attrs = dict(attrs)
            href = attrs.get('href')
            if href:
                self.current = {'href': href, 'text': ''}

    def handle_data(self, data):
        if self.current is not None:
            self.current['text'] += data

    def handle_endtag(self, tag):
        if tag == 'a' and self.current is not None:
            self.links.append(self.current)
            self.current = None

def _insert(conn, source_name, title, item_url, summary='', published=''):
    if not item_url or not title:
        return 0
    cur = execute(conn,
        "INSERT INTO jobs (source,title,url,summary,published,discovered_at,status) VALUES (?,?,?,?,?,?, 'pending') ON CONFLICT(url) DO NOTHING",
        (source_name, title[:500], item_url, summary[:5000], published[:200],
         datetime.now(timezone.utc).isoformat()))
    return 1 if cur.rowcount and cur.rowcount > 0 else 0

def _read_html_source(source):
    url = source.get('url', '').strip()
    response = requests.get(url, headers={'User-Agent': 'TechTisJobAlerts/1.0 (public recruitment notice monitor)'}, timeout=25)
    response.raise_for_status()
    parser = NoticeLinkParser()
    parser.feed(response.text)
    base_host = urlparse(url).netloc.lower()
    found = []
    seen = set()
    for link in parser.links:
        title = ' '.join(link['text'].split())
        target = urljoin(url, link['href'].strip())
        parsed = urlparse(target)
        if not title or not parsed.scheme.startswith('http') or parsed.netloc.lower() != base_host:
            continue
        if not any(word in (title + ' ' + target).lower() for word in KEYWORDS):
            continue
        if target in seen or target.rstrip('/') == url.rstrip('/'):
            continue
        seen.add(target)
        found.append((title, target))
    return found

def discover_jobs():
    if not SOURCES_FILE.exists():
        raise RuntimeError(f'Source config not found: {SOURCES_FILE}')
    config = json.loads(SOURCES_FILE.read_text(encoding='utf-8'))
    added = checked = 0
    errors = []
    with connection() as conn:
        for source in config.get('sources', []):
            if not source.get('enabled'):
                continue
            source_type = source.get('type')
            url = source.get('url', '').strip()
            if not url or 'ADD_' in url:
                errors.append(f"Placeholder URL skipped: {source.get('name')}")
                continue
            checked += 1
            try:
                if source_type == 'rss':
                    feed = feedparser.parse(url)
                    if getattr(feed, 'bozo', False) and not feed.entries:
                        errors.append(f"{source.get('name')}: feed parse failed")
                        continue
                    for entry in feed.entries:
                        item_url = entry.get('link', '').strip()
                        title = entry.get('title', 'Untitled notice').strip()
                        summary = entry.get('summary', entry.get('description', '')).strip()
                        published = entry.get('published', entry.get('updated', ''))
                        added += _insert(conn, source.get('name', 'Official source'), title, item_url, summary, published)
                elif source_type == 'html':
                    for title, item_url in _read_html_source(source):
                        added += _insert(conn, source.get('name', 'Official source'), title, item_url)
                else:
                    errors.append(f"Unsupported source type: {source_type}")
            except Exception as exc:
                errors.append(f"{source.get('name')}: {type(exc).__name__}: {exc}")
    return {'sources_checked': checked, 'new_items': added, 'errors': errors}

def get_jobs(status=None, limit=100):
    with connection() as conn:
        sql = 'SELECT id,source,title,url,summary,published,discovered_at,status,posted_at FROM jobs'
        params = []
        if status:
            sql += ' WHERE status = ?'
            params.append(status)
        sql += ' ORDER BY id DESC LIMIT ?'
        params.append(limit)
        return [dict(row) for row in execute(conn, sql, tuple(params)).fetchall()]

def approve_job(job_id):
    with connection() as conn:
        return execute(conn, "UPDATE jobs SET status='approved' WHERE id=? AND status='pending'", (job_id,)).rowcount > 0

def mark_posted(job_id):
    with connection() as conn:
        execute(conn, "UPDATE jobs SET status='posted', posted_at=? WHERE id=? AND status='approved'",
                (datetime.now(timezone.utc).isoformat(), job_id))

def delete_jobs(job_ids):
    if not job_ids:
        return 0
    with connection() as conn:
        placeholders = ','.join(['?'] * len(job_ids))
        cur = execute(conn, f"DELETE FROM jobs WHERE id IN ({placeholders})", tuple(job_ids))
        return cur.rowcount or 0
