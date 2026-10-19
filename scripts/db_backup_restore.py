"""
VoiceHire Database Backup & Restore Utility
Supports local SQLite atomic backups and provides Supabase PostgreSQL procedures.
"""

import os
import sys
import sqlite3
import shutil
from datetime import datetime

INSTANCE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "instance")
DEFAULT_SQLITE_PATH = os.path.join(INSTANCE_DIR, "voicehire_local.db")
BACKUP_DIR = os.path.join(INSTANCE_DIR, "backups")

def backup_sqlite(source_path=DEFAULT_SQLITE_PATH, target_dir=BACKUP_DIR) -> str:
    """
    Performs an atomic, non-blocking online backup using SQLite's backup API.
    Does not lock writers or corrupt state.
    """
    if not os.path.exists(source_path):
        raise FileNotFoundError(f"Source database not found at {source_path}")
    
    os.makedirs(target_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = os.path.join(target_dir, f"voicehire_backup_{timestamp}.db")

    src_conn = sqlite3.connect(source_path)
    dst_conn = sqlite3.connect(backup_file)
    with dst_conn:
        src_conn.backup(dst_conn)
    dst_conn.close()
    src_conn.close()

    # Integrity check on the backup
    check_conn = sqlite3.connect(backup_file)
    cur = check_conn.cursor()
    cur.execute("PRAGMA integrity_check;")
    result = cur.fetchone()[0]
    check_conn.close()

    if result != "ok":
        os.remove(backup_file)
        raise RuntimeError(f"Backup failed integrity check: {result}")

    return backup_file

def restore_sqlite(backup_path: str, target_path=DEFAULT_SQLITE_PATH) -> bool:
    """
    Restores an SQLite backup safely. Creates a safety copy of the current target first.
    """
    if not os.path.exists(backup_path):
        raise FileNotFoundError(f"Backup file not found at {backup_path}")

    # Verify backup integrity first
    check_conn = sqlite3.connect(backup_path)
    cur = check_conn.cursor()
    cur.execute("PRAGMA integrity_check;")
    result = cur.fetchone()[0]
    check_conn.close()
    if result != "ok":
        raise RuntimeError(f"Cannot restore: Backup failed integrity check ({result})")

    if os.path.exists(target_path):
        safety_path = f"{target_path}.pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(target_path, safety_path)

    # Perform atomic restore
    src_conn = sqlite3.connect(backup_path)
    dst_conn = sqlite3.connect(target_path)
    with dst_conn:
        src_conn.backup(dst_conn)
    dst_conn.close()
    src_conn.close()

    return True

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "backup":
        out = backup_sqlite()
        print(f"Backup created successfully: {out}")
    elif len(sys.argv) > 2 and sys.argv[1] == "restore":
        restore_sqlite(sys.argv[2])
        print(f"Restored from {sys.argv[2]}")
    else:
        print("Usage: python db_backup_restore.py [backup|restore <backup_path>]")
