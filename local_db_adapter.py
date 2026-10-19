"""
VoiceHire — Resilient Local Database Adapter
═══════════════════════════════════════════════════════════════════════════════
Provides a persistent SQLite-backed PostgREST query engine when the remote
Supabase endpoint is unreachable (e.g. non-existent domain / offline / DNS block).

Features:
  - Strict compliance with PostgREST query builder API:
      select(), eq(), neq(), in_(), ilike(), order(), limit(),
      insert(), update(), delete(), execute()
  - Persistent ACID storage backed by SQLite in `instance/voicehire_local.db`
  - Survives application restarts, browser reloads, and re-logins
  - Pre-seeds initial demo accounts (e.g. Raju Sharma) if tables are empty
  - Transparently falls back if live Supabase throws ConnectError/gaierror
═══════════════════════════════════════════════════════════════════════════════
"""

import json
import logging
import os
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash

logger = logging.getLogger("VoiceHire.LocalDB")

_lock = threading.Lock()


class PostgrestResponse:
    """Matches postgrest-py API response structure."""
    def __init__(self, data):
        self.data = data if data is not None else []

    def __repr__(self):
        return f"<PostgrestResponse data={len(self.data)} rows>"


class LocalTableQuery:
    """In-memory & SQLite-backed PostgREST query builder."""

    def __init__(self, db_path: str, table_name: str):
        self._db_path = db_path
        self._table = table_name
        self._selected_cols = "*"
        self._filters = []       # list of (op, col, val)
        self._order_col = None
        self._order_desc = False
        self._limit = None
        self._pending_action = "select" # "select", "insert", "update", "delete"
        self._pending_data = None
        self._last_result = None

    def select(self, cols="*"):
        self._selected_cols = cols
        self._pending_action = "select"
        return self

    def eq(self, col: str, val):
        self._filters.append(("eq", col, val))
        return self

    def neq(self, col: str, val):
        self._filters.append(("neq", col, val))
        return self

    def in_(self, col: str, values):
        self._filters.append(("in", col, list(values)))
        return self

    def ilike(self, col: str, pattern: str):
        clean = pattern.replace("%", "").lower()
        self._filters.append(("ilike", col, clean))
        return self

    def order(self, col: str, desc: bool = False):
        self._order_col = col
        self._order_desc = desc
        return self

    def limit(self, n: int):
        self._limit = int(n)
        return self

    def insert(self, record_or_records):
        self._pending_action = "insert"
        self._pending_data = record_or_records
        return self

    def update(self, updates: dict):
        self._pending_action = "update"
        self._pending_data = dict(updates)
        return self

    def delete(self):
        self._pending_action = "delete"
        return self

    def _get_connection(self):
        conn = sqlite3.connect(self._db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _matches_filters(self, row_dict: dict) -> bool:
        for op, col, val in self._filters:
            row_val = row_dict.get(col)
            if op == "eq":
                # Handle numeric / string comparisons
                if str(row_val) != str(val):
                    return False
            elif op == "neq":
                if str(row_val) == str(val):
                    return False
            elif op == "in":
                val_strs = [str(x) for x in val]
                if str(row_val) not in val_strs:
                    return False
            elif op == "ilike":
                if val not in str(row_val or "").lower():
                    return False
        return True

    def execute(self) -> PostgrestResponse:
        with _lock:
            conn = self._get_connection()
            try:
                cursor = conn.cursor()

                if self._pending_action == "insert":
                    items = self._pending_data
                    if isinstance(items, dict):
                        items = [items]
                    elif not isinstance(items, list):
                        items = [dict(items)]

                    inserted = []
                    for item in items:
                        r = dict(item)
                        rec_id = str(r.get("id") or uuid.uuid4())
                        r["id"] = rec_id
                        now_iso = datetime.now(timezone.utc).isoformat()
                        if "created_at" not in r:
                            r["created_at"] = now_iso
                        if "updated_at" not in r:
                            r["updated_at"] = now_iso

                        data_json = json.dumps(r)
                        cursor.execute(
                            "INSERT OR REPLACE INTO vh_records (table_name, record_id, data) VALUES (?, ?, ?)",
                            (self._table, rec_id, data_json)
                        )
                        inserted.append(r)
                    conn.commit()
                    return PostgrestResponse(inserted)

                # Fetch all rows for this table to apply filters & mutations
                cursor.execute(
                    "SELECT record_id, data FROM vh_records WHERE table_name = ?",
                    (self._table,)
                )
                rows = cursor.fetchall()
                parsed_rows = []
                for row in rows:
                    try:
                        d = json.loads(row["data"])
                        parsed_rows.append(d)
                    except Exception:
                        pass

                matched = [r for r in parsed_rows if self._matches_filters(r)]

                if self._pending_action == "update":
                    updates = dict(self._pending_data or {})
                    now_iso = datetime.now(timezone.utc).isoformat()
                    updates["updated_at"] = now_iso
                    updated_rows = []
                    for r in matched:
                        r.update(updates)
                        rec_id = str(r["id"])
                        data_json = json.dumps(r)
                        cursor.execute(
                            "UPDATE vh_records SET data = ? WHERE table_name = ? AND record_id = ?",
                            (data_json, self._table, rec_id)
                        )
                        updated_rows.append(r)
                    conn.commit()
                    return PostgrestResponse(updated_rows)

                elif self._pending_action == "delete":
                    for r in matched:
                        rec_id = str(r["id"])
                        cursor.execute(
                            "DELETE FROM vh_records WHERE table_name = ? AND record_id = ?",
                            (self._table, rec_id)
                        )
                    conn.commit()
                    return PostgrestResponse(matched)

                else:  # "select"
                    # Apply ordering if requested
                    if self._order_col:
                        matched.sort(
                            key=lambda x: str(x.get(self._order_col, "")),
                            reverse=self._order_desc
                        )

                    # Apply limit
                    if self._limit is not None:
                        matched = matched[:self._limit]

                    return PostgrestResponse(matched)

            finally:
                conn.close()


class LocalPostgrestClient:
    """Drop-in replacement for Supabase Client with persistent local SQLite storage."""

    def __init__(self, db_path: str = "instance/voicehire_local.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vh_records (
                table_name  TEXT NOT NULL,
                record_id   TEXT NOT NULL,
                data        TEXT NOT NULL,
                PRIMARY KEY (table_name, record_id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_vh_table ON vh_records(table_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_vh_record ON vh_records(record_id)")
        conn.commit()

        # Seed initial demo workers & customer if table is empty
        cursor.execute("SELECT count(*) FROM vh_records WHERE table_name = 'workers'")
        worker_count = cursor.fetchone()[0]
        if worker_count == 0:
            self._seed_default_data(cursor)
            conn.commit()

        conn.close()

    def _seed_default_data(self, cursor):
        now_iso = datetime.now(timezone.utc).isoformat()
        default_pw = generate_password_hash("WorkerPass@123")

        # 1. Default Worker Raju Sharma
        w1_id = "worker-raju-sharma-1"
        w1 = {
            "id": w1_id,
            "name": "Raju Sharma",
            "phone": "9876543210",
            "password": default_pw,
            "work": "Electrician",
            "location": "Sector 62, Noida",
            "price": 500.0,
            "experience_years": 5,
            "bio": "Experienced licensed electrician for all residential wiring and repair.",
            "service_radius_km": 20,
            "quote_preference": "estimate_then_confirm",
            "is_available": True,
            "is_verified": False,
            "verification_status": "unsubmitted",
            "payout_status": "unconfigured",
            "language_preference": "hi",
            "created_at": now_iso,
            "updated_at": now_iso
        }
        cursor.execute(
            "INSERT OR REPLACE INTO vh_records (table_name, record_id, data) VALUES (?, ?, ?)",
            ("workers", w1_id, json.dumps(w1))
        )

        # 2. Worker skills
        s1 = {"id": "skill-1", "worker_id": w1_id, "skill": "House Wiring", "is_primary": True, "created_at": now_iso}
        s2 = {"id": "skill-2", "worker_id": w1_id, "skill": "MCB & Fuse Repair", "is_primary": False, "created_at": now_iso}
        cursor.execute("INSERT OR REPLACE INTO vh_records VALUES (?, ?, ?)", ("worker_skills", "skill-1", json.dumps(s1)))
        cursor.execute("INSERT OR REPLACE INTO vh_records VALUES (?, ?, ?)", ("worker_skills", "skill-2", json.dumps(s2)))

        # 3. Default Customer Anita Verma
        c1_id = "customer-anita-verma-1"
        c1 = {
            "id": c1_id,
            "name": "Anita Verma",
            "phone": "9899988877",
            "password": generate_password_hash("CustomerPass@123"),
            "role": "user",
            "locality": "Sector 62, Noida",
            "language_preference": "hi",
            "created_at": now_iso,
            "updated_at": now_iso
        }
        cursor.execute("INSERT OR REPLACE INTO vh_records VALUES (?, ?, ?)", ("users", c1_id, json.dumps(c1)))

    def table(self, table_name: str) -> LocalTableQuery:
        return LocalTableQuery(self.db_path, table_name)


def get_resilient_supabase_client(supabase_url: str, supabase_key: str):
    """
    Returns live Supabase Client if reachable; falls back to persistent
    local SQLite PostgREST adapter if network/DNS resolution fails.
    """
    # Check if force local db is enabled via env
    if os.environ.get("VOICEHIRE_LOCAL_DB", "").lower() in ("1", "true"):
        logger.info("[Database] VOICEHIRE_LOCAL_DB=1 requested. Using persistent local SQLite storage.")
        return LocalPostgrestClient()

    try:
        from supabase import create_client
        client = create_client(supabase_url, supabase_key)
        # Fast health-check query
        client.table("users").select("id").limit(1).execute()
        logger.info("[Database] Connected successfully to remote Supabase endpoint.")
        return client
    except Exception as e:
        logger.warning(
            f"[Database] Remote Supabase endpoint unavailable ({type(e).__name__}: {e}). "
            "Switching automatically to persistent local SQLite storage (instance/voicehire_local.db)."
        )
        return LocalPostgrestClient()
