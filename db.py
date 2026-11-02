import os
import sqlite3
from contextlib import contextmanager
DATABASE_URL = os.getenv('DATABASE_URL', '').strip()
SQLITE_PATH = os.getenv('DATABASE_PATH', 'jobs.db')

@contextmanager
def connection():
    if DATABASE_URL:
        import psycopg
        from psycopg.rows import dict_row
        conn = psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=15)
        try:
            yield conn; conn.commit()
        except Exception:
            conn.rollback(); raise
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(SQLITE_PATH); conn.row_factory = sqlite3.Row
        try:
            conn.execute('''CREATE TABLE IF NOT EXISTS jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL, title TEXT NOT NULL, url TEXT NOT NULL UNIQUE, summary TEXT, published TEXT, discovered_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', posted_at TEXT)''')
            yield conn; conn.commit()
        except Exception:
            conn.rollback(); raise
        finally:
            conn.close()

def execute(conn, sql, params=()):
    return conn.execute(sql.replace('?', '%s'), params) if DATABASE_URL else conn.execute(sql, params)
