from fastapi import APIRouter, Request
import sqlite3
import os

router = APIRouter()

DB_PATH = os.path.join(os.path.dirname(__file__), "metrics.db")


# ✅ Initialize DB
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS counter (
            key TEXT PRIMARY KEY,
            value INTEGER NOT NULL
        )
    """)

    # initialize visits counter
    cur.execute("INSERT OR IGNORE INTO counter(key, value) VALUES('visits', 0)")

    conn.commit()
    conn.close()


init_db()


# ✅ Increment visit
@router.post("/api/metrics/visit")
def record_visit(request: Request):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("UPDATE counter SET value = value + 1 WHERE key='visits'")
    conn.commit()

    cur.execute("SELECT value FROM counter WHERE key='visits'")
    visits = cur.fetchone()[0]

    conn.close()

    return {"total_visits": visits}


# ✅ Get stats
@router.get("/api/metrics/stats")
def get_stats():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT value FROM counter WHERE key='visits'")
    visits = cur.fetchone()[0]

    conn.close()

    return {"total_visits": visits}
