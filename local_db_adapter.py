"""
VoiceHire — Database Adapter & Resilient Mode Engine
═══════════════════════════════════════════════════════════════════════════════
Phase 15: Explicit Database Mode, Hardened Supabase Verification,
Strict Rejection of Silent Fallback in Staging/Production, and
Full-Featured PostgREST SQLite Adapter for Local Development & Testing.
═══════════════════════════════════════════════════════════════════════════════
"""

import json
import logging
import os
import re
import socket
import sqlite3
import threading
import urllib.parse
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from werkzeug.security import generate_password_hash

logger = logging.getLogger("VoiceHire.Database")

_lock = threading.Lock()


# ─────────────────────────────────────────────────────────────────────────────
# 1. DATABASE EXCEPTIONS
# ─────────────────────────────────────────────────────────────────────────────
class DatabaseConfigurationError(Exception):
    """Raised when required database environment variables are missing or malformed."""
    pass


class DatabaseConnectionError(Exception):
    """Raised when the configured database endpoint is unreachable or DNS fails."""
    pass


class DatabaseModeError(Exception):
    """Raised when an invalid or prohibited database mode is requested for the environment."""
    pass


# ─────────────────────────────────────────────────────────────────────────────
# 2. POSTGREST RESPONSE SHAPE
# ─────────────────────────────────────────────────────────────────────────────
class PostgrestResponse:
    """Strictly matches postgrest-py / supabase-py response contract."""
    def __init__(self, data: Optional[List[Dict[str, Any]]] = None, count: Optional[int] = None):
        self.data = data if data is not None else []
        self.count = count if count is not None else len(self.data)

    def __repr__(self):
        return f"<PostgrestResponse data={len(self.data)} rows, count={self.count}>"


# ─────────────────────────────────────────────────────────────────────────────
# 3. SQLITE POSTGREST QUERY BUILDER
# ─────────────────────────────────────────────────────────────────────────────
class LocalTableQuery:
    """
    ACID-compliant SQLite-backed PostgREST query builder.
    Full compatibility with PostgREST query operations across VoiceHire:
      - select(), insert(), update(), delete(), execute()
      - eq(), neq(), gt(), gte(), lt(), lte(), in_(), ilike(), like(), is_(), contains()
      - order(), limit()
    """

    def __init__(self, conn_or_path: Any, table_name: str):
        if isinstance(conn_or_path, sqlite3.Connection):
            self._conn = conn_or_path
            self._db_path = None
        else:
            self._db_path = conn_or_path
            self._conn = None
        self._table = table_name
        self._selected_cols = "*"
        self._filters: List[Tuple[str, str, Any]] = []  # list of (op, col, val)
        self._order_col: Optional[str] = None
        self._order_desc: bool = False
        self._limit: Optional[int] = None
        self._pending_action: str = "select"  # "select", "insert", "update", "delete"
        self._pending_data: Any = None

    def select(self, cols: str = "*"):
        self._selected_cols = cols
        self._pending_action = "select"
        return self

    def eq(self, col: str, val: Any):
        self._filters.append(("eq", col, val))
        return self

    def neq(self, col: str, val: Any):
        self._filters.append(("neq", col, val))
        return self

    def gt(self, col: str, val: Any):
        self._filters.append(("gt", col, val))
        return self

    def gte(self, col: str, val: Any):
        self._filters.append(("gte", col, val))
        return self

    def lt(self, col: str, val: Any):
        self._filters.append(("lt", col, val))
        return self

    def lte(self, col: str, val: Any):
        self._filters.append(("lte", col, val))
        return self

    def in_(self, col: str, values: Any):
        self._filters.append(("in", col, list(values)))
        return self

    def ilike(self, col: str, pattern: str):
        clean = pattern.replace("%", "").lower()
        self._filters.append(("ilike", col, clean))
        return self

    def like(self, col: str, pattern: str):
        clean = pattern.replace("%", "")
        self._filters.append(("like", col, clean))
        return self

    def is_(self, col: str, val: Any):
        self._filters.append(("is", col, val))
        return self

    def contains(self, col: str, val: Any):
        self._filters.append(("contains", col, val))
        return self

    def order(self, col: str, desc: bool = False):
        self._order_col = col
        self._order_desc = desc
        return self

    def limit(self, n: int):
        self._limit = int(n)
        return self

    def insert(self, record_or_records: Any):
        self._pending_action = "insert"
        self._pending_data = record_or_records
        return self

    def update(self, updates: Dict[str, Any]):
        self._pending_action = "update"
        self._pending_data = dict(updates)
        return self

    def delete(self):
        self._pending_action = "delete"
        return self

    def _get_connection(self):
        if self._conn is not None:
            return self._conn, False
        conn = sqlite3.connect(self._db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        return conn, True

    def _matches_filters(self, row_dict: Dict[str, Any]) -> bool:
        for op, col, val in self._filters:
            row_val = row_dict.get(col)

            if op == "eq":
                if val is None:
                    if row_val is not None:
                        return False
                elif isinstance(val, bool) or isinstance(row_val, bool):
                    if bool(row_val) != bool(val):
                        return False
                else:
                    # Compare as numeric if both can convert, else as string
                    try:
                        if float(row_val) != float(val):
                            return False
                    except (ValueError, TypeError):
                        if str(row_val) != str(val):
                            return False

            elif op == "neq":
                if val is None:
                    if row_val is None:
                        return False
                elif isinstance(val, bool) or isinstance(row_val, bool):
                    if bool(row_val) == bool(val):
                        return False
                else:
                    try:
                        if float(row_val) == float(val):
                            return False
                    except (ValueError, TypeError):
                        if str(row_val) == str(val):
                            return False

            elif op == "gt":
                try:
                    if float(row_val) <= float(val):
                        return False
                except (ValueError, TypeError):
                    if str(row_val) <= str(val):
                        return False

            elif op == "gte":
                try:
                    if float(row_val) < float(val):
                        return False
                except (ValueError, TypeError):
                    if str(row_val) < str(val):
                        return False

            elif op == "lt":
                try:
                    if float(row_val) >= float(val):
                        return False
                except (ValueError, TypeError):
                    if str(row_val) >= str(val):
                        return False

            elif op == "lte":
                try:
                    if float(row_val) > float(val):
                        return False
                except (ValueError, TypeError):
                    if str(row_val) > str(val):
                        return False

            elif op == "in":
                val_strs = [str(x) for x in val]
                if str(row_val) not in val_strs:
                    return False

            elif op == "ilike":
                if str(val).lower() not in str(row_val or "").lower():
                    return False

            elif op == "like":
                if str(val) not in str(row_val or ""):
                    return False

            elif op == "is":
                if val is None or str(val).lower() == "null":
                    if row_val is not None:
                        return False
                elif row_val is not val:
                    return False

            elif op == "contains":
                if isinstance(row_val, list):
                    if val not in row_val:
                        return False
                elif str(val) not in str(row_val or ""):
                    return False

        return True

    def _project_columns(self, row: Dict[str, Any]) -> Dict[str, Any]:
        if not self._selected_cols or self._selected_cols == "*":
            return dict(row)
        cols = [c.strip() for c in self._selected_cols.split(",") if c.strip()]
        if "*" in cols:
            return dict(row)
        return {c: row[c] for c in cols if c in row}

    def execute(self) -> PostgrestResponse:
        with _lock:
            conn, should_close = self._get_connection()
            try:
                cursor = conn.cursor()

                # ── INSERT ─────────────────────────────────────────────────────
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
                        inserted.append(self._project_columns(r))
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

                # ── UPDATE ─────────────────────────────────────────────────────
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
                        updated_rows.append(self._project_columns(r))
                    conn.commit()
                    return PostgrestResponse(updated_rows)

                # ── DELETE ─────────────────────────────────────────────────────
                elif self._pending_action == "delete":
                    for r in matched:
                        rec_id = str(r["id"])
                        cursor.execute(
                            "DELETE FROM vh_records WHERE table_name = ? AND record_id = ?",
                            (self._table, rec_id)
                        )
                    conn.commit()
                    return PostgrestResponse([self._project_columns(r) for r in matched])

                # ── SELECT ─────────────────────────────────────────────────────
                else:
                    if self._order_col:
                        def _sort_key(item):
                            v = item.get(self._order_col)
                            if v is None:
                                return ""
                            try:
                                return float(v)
                            except (ValueError, TypeError):
                                return str(v)

                        matched.sort(key=_sort_key, reverse=self._order_desc)

                    if self._limit is not None:
                        matched = matched[:self._limit]

                    return PostgrestResponse([self._project_columns(r) for r in matched])

            finally:
                if should_close:
                    conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# 4. LOCAL POSTGREST CLIENT
# ─────────────────────────────────────────────────────────────────────────────
class LocalPostgrestClient:
    """Drop-in Supabase Client implementation backed by persistent local SQLite."""

    def __init__(self, db_path: str = "instance/voicehire_local.db"):
        self.db_path = db_path
        if db_path != ":memory:":
            db_dir = os.path.dirname(os.path.abspath(db_path))
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        with _lock:
            cursor = self._conn.cursor()
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
            self._conn.commit()

            cursor.execute("SELECT count(*) FROM vh_records WHERE table_name = 'workers'")
            worker_count = cursor.fetchone()[0]
            if worker_count == 0:
                self._seed_default_data(cursor)
                self._conn.commit()

    def _seed_default_data(self, cursor):
        now_iso = datetime.now(timezone.utc).isoformat()
        default_pw = generate_password_hash("WorkerPass@123")

        # Default Worker Raju Sharma
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

        s1 = {"id": "skill-1", "worker_id": w1_id, "skill": "House Wiring", "is_primary": True, "created_at": now_iso}
        s2 = {"id": "skill-2", "worker_id": w1_id, "skill": "MCB & Fuse Repair", "is_primary": False, "created_at": now_iso}
        cursor.execute("INSERT OR REPLACE INTO vh_records VALUES (?, ?, ?)", ("worker_skills", "skill-1", json.dumps(s1)))
        cursor.execute("INSERT OR REPLACE INTO vh_records VALUES (?, ?, ?)", ("worker_skills", "skill-2", json.dumps(s2)))

        # Default Customer Anita Verma
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
        return LocalTableQuery(self._conn, table_name)

    def ping(self) -> bool:
        """Pings SQLite database to confirm read/write availability."""
        try:
            with _lock:
                cur = self._conn.cursor()
                cur.execute("SELECT 1")
                res = cur.fetchone()
                return res is not None and res[0] == 1
        except Exception:
            return False

    def get_mode_info(self) -> Dict[str, Any]:
        """Returns non-sensitive metadata for liveness/readiness probes."""
        return {
            "mode": "sqlite_development",
            "connected": self.ping(),
            "path": self.db_path,
            "is_disposable_test_mode": ":memory:" in self.db_path or "test_" in os.path.basename(self.db_path)
        }


# ─────────────────────────────────────────────────────────────────────────────
# 5. SUPABASE CONNECTIVITY & VERIFICATION
# ─────────────────────────────────────────────────────────────────────────────
def check_supabase_connectivity(url: str, key: str, timeout_sec: float = 4.0) -> Tuple[bool, str]:
    """
    Verifies that the Supabase host exists in public DNS and is reachable.
    Does NOT log or disclose secret credentials.
    """
    if not url or not key:
        return False, "Missing SUPABASE_URL or SUPABASE_KEY"

    try:
        parsed = urllib.parse.urlparse(url)
        host = parsed.hostname
        if not host:
            return False, f"Invalid URL format: '{url}'"

        # 1. Authoritative DNS resolution check
        try:
            socket.gethostbyname(host)
        except socket.gaierror as dns_err:
            return False, f"DNS resolution failed for '{host}' (getaddrinfo failed). Host does not exist or project was paused."

        # 2. Live PostgREST query check
        from supabase import create_client
        client = create_client(url, key)
        resp = client.table("users").select("id").limit(1).execute()
        return True, "Supabase connection active and verified."
    except Exception as e:
        return False, f"Supabase connection error: {type(e).__name__} ({e})"


# ─────────────────────────────────────────────────────────────────────────────
# 6. EXPLICIT DATABASE MODE RESOLVER
# ─────────────────────────────────────────────────────────────────────────────
def get_database_client(
    supabase_url: Optional[str] = None,
    supabase_key: Optional[str] = None,
    app_env: Optional[str] = None,
    db_mode: Optional[str] = None,
    sqlite_path: Optional[str] = None
) -> Tuple[Any, Dict[str, Any]]:
    """
    Resolves the authoritative database client enforcing strict mode boundaries.

    Rules:
      1. In STAGING or PRODUCTION (app_env in 'staging', 'production'):
         - SQLite fallback is STRICTLY FORBIDDEN.
         - Supabase connection MUST be verified and active.
         - Raises DatabaseConnectionError or DatabaseModeError on failure.
      2. In DEVELOPMENT with explicit SQLite (db_mode in 'sqlite', 'local'):
         - Uses LocalPostgrestClient backed by SQLite.
         - SQLite is never mistaken for Supabase.
      3. In DEVELOPMENT without explicit mode:
         - If Supabase connects, uses Supabase.
         - If Supabase fails, falls back to SQLite with an explicit warning.
    """
    env = (app_env or os.environ.get("APP_ENV") or os.environ.get("FLASK_ENV") or "development").lower().strip()
    is_prod_or_staging = env in ("production", "staging")

    mode = (db_mode or os.environ.get("VOICEHIRE_DB_MODE") or os.environ.get("DB_MODE") or "").lower().strip()
    force_local = os.environ.get("VOICEHIRE_LOCAL_DB", "").lower() in ("1", "true")

    url = supabase_url or os.environ.get("SUPABASE_URL")
    key = supabase_key or os.environ.get("SUPABASE_KEY")
    db_path = sqlite_path or os.environ.get("VOICEHIRE_SQLITE_PATH", "instance/voicehire_local.db")

    # ── RULE 1: Staging / Production Guard ──────────────────────────────────
    if is_prod_or_staging:
        # If SQLite is explicitly requested in staging/production, strictly prohibit it
        if db_mode in ("sqlite", "local"):
            raise DatabaseModeError(
                f"CRITICAL CONFIGURATION ERROR: SQLite database mode is strictly prohibited "
                f"in environment '{env}'. Staging and Production must use verified Supabase."
            )

        if not url or not key:
            raise DatabaseConfigurationError(
                f"CRITICAL CONFIGURATION ERROR: SUPABASE_URL and SUPABASE_KEY are required in environment '{env}'."
            )

        conn_ok, conn_msg = check_supabase_connectivity(url, key)
        if not conn_ok:
            raise DatabaseConnectionError(
                f"CRITICAL: Failed to connect to remote Supabase in environment '{env}': {conn_msg}. "
                f"Silent fallback to SQLite is strictly forbidden. Refusing to start."
            )

        from supabase import create_client
        client = create_client(url, key)
        meta = {"mode": "supabase_production" if env == "production" else "supabase_staging", "connected": True, "url_host": urllib.parse.urlparse(url).hostname}
        logger.info(f"[Database] Verified active Supabase connection in {env} mode.")
        return client, meta

    # ── RULE 2: Explicit Local Development with SQLite ──────────────────────
    if mode in ("sqlite", "local") or force_local:
        client = LocalPostgrestClient(db_path=db_path)
        meta = client.get_mode_info()
        logger.info(f"[Database] Explicit SQLite Local Development Mode active ({db_path}).")
        return client, meta

    # ── RULE 3: Explicit Supabase Mode Requested in Development ─────────────
    if mode in ("supabase", "remote"):
        if not url or not key:
            raise DatabaseConfigurationError("SUPABASE_URL and SUPABASE_KEY required when VOICEHIRE_DB_MODE=supabase.")
        conn_ok, conn_msg = check_supabase_connectivity(url, key)
        if not conn_ok:
            raise DatabaseConnectionError(
                f"Failed to connect to Supabase (VOICEHIRE_DB_MODE=supabase): {conn_msg}. "
                "Refusing SQLite fallback because remote mode was explicitly requested."
            )
        from supabase import create_client
        client = create_client(url, key)
        meta = {"mode": "supabase_development", "connected": True, "url_host": urllib.parse.urlparse(url).hostname}
        return client, meta

    # ── RULE 4: Development Auto-Resolution ─────────────────────────────────
    if url and key and not url.startswith("https://your-"):
        conn_ok, conn_msg = check_supabase_connectivity(url, key)
        if conn_ok:
            from supabase import create_client
            client = create_client(url, key)
            meta = {"mode": "supabase_development", "connected": True, "url_host": urllib.parse.urlparse(url).hostname}
            logger.info("[Database] Connected successfully to remote Supabase endpoint in development.")
            return client, meta
        else:
            logger.warning(
                f"[Database Notice] Remote Supabase endpoint unavailable in development: {conn_msg}. "
                f"Switching to persistent local SQLite storage ({db_path}). "
                f"To make this explicit, set VOICEHIRE_DB_MODE=sqlite in .env."
            )

    client = LocalPostgrestClient(db_path=db_path)
    meta = client.get_mode_info()
    return client, meta


def get_resilient_supabase_client(supabase_url: Optional[str] = None, supabase_key: Optional[str] = None):
    """Backward-compatible entry point for existing modules."""
    client, _ = get_database_client(supabase_url=supabase_url, supabase_key=supabase_key)
    return client
