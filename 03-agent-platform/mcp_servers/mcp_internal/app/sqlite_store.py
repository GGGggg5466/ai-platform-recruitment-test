import os
import sqlite3
from typing import Any, Dict, List, Tuple, Optional

DEFAULT_SQLITE_PATH = os.getenv("SQLITE_PATH", "/app/data/app.db")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  dept TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
  id INTEGER PRIMARY KEY,
  user_id INTEGER NOT NULL,
  item TEXT NOT NULL,
  amount INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(user_id) REFERENCES users(id)
);
"""

SEED_SQL = """
INSERT OR IGNORE INTO users(id, name, dept) VALUES
  (1,'Alice','AI'),
  (2,'Bob','Platform'),
  (3,'Carol','Research');

INSERT OR IGNORE INTO orders(id, user_id, item, amount, created_at) VALUES
  (101,1,'latte',80,'2026-02-18T09:12:00'),
  (102,2,'sandwich',120,'2026-02-18T10:01:00'),
  (103,1,'tea',50,'2026-02-19T13:45:00');
"""

# Whitelist-only queries: query_id -> (sql, required_params)
SAFE_QUERIES: Dict[str, Tuple[str, List[str]]] = {
    "list_users": (
        "SELECT id, name, dept FROM users ORDER BY id ASC;",
        [],
    ),
    "get_user_by_id": (
        "SELECT id, name, dept FROM users WHERE id = :user_id;",
        ["user_id"],
    ),
    "recent_orders": (
        "SELECT id, user_id, item, amount, created_at FROM orders ORDER BY created_at DESC LIMIT :limit;",
        ["limit"],
    ),
    "sum_orders_by_user": (
        "SELECT user_id, SUM(amount) AS total_amount FROM orders GROUP BY user_id ORDER BY user_id ASC;",
        [],
    ),
}


def get_conn(sqlite_path: Optional[str] = DEFAULT_SQLITE_PATH) -> sqlite3.Connection:
    sqlite_path = sqlite_path or DEFAULT_SQLITE_PATH
    os.makedirs(os.path.dirname(sqlite_path), exist_ok=True)
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(sqlite_path: Optional[str] = DEFAULT_SQLITE_PATH) -> None:
    conn = get_conn(sqlite_path)
    try:
        conn.executescript(SCHEMA_SQL)
        conn.executescript(SEED_SQL)
        conn.commit()
    finally:
        conn.close()


def run_safe_query(
    query_id: str,
    params: Dict[str, Any],
    sqlite_path: Optional[str] = DEFAULT_SQLITE_PATH,
) -> List[Dict[str, Any]]:
    if query_id not in SAFE_QUERIES:
        raise ValueError("query_id_not_allowed")

    sql, required = SAFE_QUERIES[query_id]
    for k in required:
        if k not in params:
            raise ValueError(f"missing_param:{k}")

    # defaults / coercions
    if query_id == "recent_orders":
        limit = int(params.get("limit", 5))
        limit = max(1, min(limit, 20))
        params = dict(params)
        params["limit"] = limit

    conn = get_conn(sqlite_path)
    try:
        cur = conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()
