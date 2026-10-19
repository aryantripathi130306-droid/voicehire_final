# VOICEHIRE DATABASE BACKUP AND DISASTER RECOVERY RUNBOOK

This runbook establishes standard operating procedures (SOP) for data protection, continuous backup, snapshot verification, and point-in-time recovery for the VoiceHire platform across both SQLite local development/testing and Supabase PostgreSQL staging/production environments.

---

## 1. BACKUP & STORAGE ARCHITECTURE

VoiceHire operates in two explicitly isolated database modes controlled by `VOICEHIRE_DB_MODE` and `APP_ENV`:

| Database Engine | Intended Environment | Storage Location / Service | Frequency | Retention Policy |
| :--- | :--- | :--- | :--- | :--- |
| **SQLite (`local_db_adapter`)** | Development, CI/CD, Local Sandboxes | `instance/voicehire_local.db` | On-demand / Pre-migration | 30 days |
| **Supabase (PostgreSQL 15+)** | Staging, Production | Supabase Cloud (Managed AWS/GCP) | Daily automated snapshots + Continuous WAL | 7 days (Free/Pro) / 30 days (Enterprise) |

---

## 2. SQLITE BACKUP & RESTORATION (LOCAL / TESTING)

### 2.1 Online Non-Blocking Backup
SQLite uses WAL (Write-Ahead Logging) and the native `sqlite3.backup` API to produce non-blocking, consistent binary snapshots without locking active web transactions.

**Automated Command:**
```bash
python scripts/db_backup_restore.py backup
```

**Alternative Direct CLI:**
```bash
sqlite3 instance/voicehire_local.db "VACUUM INTO 'instance/backups/voicehire_backup_manual.db'"
```

### 2.2 Backup Integrity Validation
Before accepting any backup file, verify that page allocation and B-Tree indexes are uncorrupted:
```bash
sqlite3 instance/backups/voicehire_backup_<timestamp>.db "PRAGMA integrity_check;"
# Expected Output: "ok"
```

### 2.3 Disaster Recovery Procedure
1. **Stop Application:**
   Stop the running Flask server or Gunicorn daemon:
   ```bash
   # Terminate dev process or systemd service
   pkill -f "python app.py"
   ```
2. **Execute Safe Restore:**
   The restore script automatically creates a pre-restore safety copy (`.pre_restore_<timestamp>`) before overwriting:
   ```bash
   python scripts/db_backup_restore.py restore instance/backups/voicehire_backup_<timestamp>.db
   ```
3. **Verify Health:**
   Restart the service and check the readiness probe:
   ```bash
   curl http://localhost:5000/health/readiness
   # Expected: {"status":"healthy","database":{"status":"connected","mode":"sqlite"}}
   ```

---

## 3. SUPABASE POSTGRESQL BACKUP & RESTORATION (STAGING / PRODUCTION)

### 3.1 Logical Backup via pg_dump / Supabase CLI
Logical backups export schema definitions, types, constraints, and table records in SQL format.

**Export Full Schema and Data:**
```bash
# Using Supabase CLI (Authenticated via access token)
supabase db dump --project-ref <PROJECT_ID> -f backups/supabase_prod_$(date +%Y%m%d_%H%M%S).sql

# Using standard PostgreSQL pg_dump over SSL
pg_dump --clean --if-exists --no-owner --no-privileges \
  -d "postgresql://postgres.[PROJECT_REF]:[DB_PASSWORD]@[DB_HOST]:5432/postgres?sslmode=require" \
  -f backups/voicehire_pg_dump_$(date +%Y%m%d_%H%M%S).sql
```

### 3.2 Point-In-Time-Recovery (PITR)
For production databases with WAL archiving enabled on Supabase:
1. Navigate to **Supabase Dashboard** -> **Project Settings** -> **Database** -> **Backups**.
2. Select **Point-in-Time Recovery**.
3. Specify the target restore timestamp (down to the exact second prior to incident/corruption).
4. Initiate restore to a new target instance or restore in-place.

### 3.3 Logical Restore from SQL Dump
1. **Maintenance Mode:**
   Direct edge proxy or reverse proxy (Cloudflare/Nginx) to return 503 Maintenance page.
2. **Apply Restore:**
   ```bash
   psql "postgresql://postgres.[PROJECT_REF]:[DB_PASSWORD]@[DB_HOST]:5432/postgres?sslmode=require" \
     -f backups/voicehire_pg_dump_<timestamp>.sql
   ```
3. **Verify Migrations:**
   Ensure all migrations from `supabase/migrations/` are applied:
   ```bash
   supabase db push
   ```
4. **Run Smoke Tests & Readiness Probe:**
   ```bash
   curl -I https://api.voicehire.in/health/readiness
   # Status 200 OK
   ```

---

## 4. PRE-DEPLOYMENT BACKUP PROTOCOL

Before applying any schema migration or releasing an update:
1. Trigger an on-demand snapshot:
   - For SQLite: Run `python scripts/db_backup_restore.py backup`.
   - For Supabase: Run `supabase db dump` and note the WAL checkpoint.
2. Validate table row counts before migration:
   - `users`, `worker_profiles`, `customer_profiles`, `jobs`, `bookings`, `payments`.
3. Apply migration script in transaction wrapper (`BEGIN; ... COMMIT;`).
4. Re-check readiness probe `/health/readiness`.

---

## 5. RECOVERY TIME OBJECTIVE (RTO) & RECOVERY POINT OBJECTIVE (RPO)

| Metric | SQLite Target | Supabase Staging Target | Supabase Production Target |
| :--- | :--- | :--- | :--- |
| **RPO (Max Data Loss Window)** | < 1 hour (manual backups) | < 24 hours (daily dump) | < 2 minutes (WAL PITR) |
| **RTO (Max Downtime to Restore)**| < 5 minutes | < 15 minutes | < 30 minutes |

---

## 6. AUDIT & DISASTER ESCALATION CONTACTS

- **Engineering Lead / Security Officer:** DevOps / Lead Engineer
- **Database Administrator:** Reliability Team
- **Incident Channel:** `#incident-voicehire`
