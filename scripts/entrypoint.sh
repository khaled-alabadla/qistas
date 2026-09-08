#!/usr/bin/env bash
set -euo pipefail

# Wait for Postgres.
python - <<'PY'
import os, time, sys
import psycopg
url = os.environ.get("DATABASE_URL", "")
for attempt in range(30):
    try:
        psycopg.connect(url, connect_timeout=3).close()
        print("database is ready")
        break
    except Exception as exc:  # noqa: BLE001
        print(f"waiting for database ({attempt+1}/30): {exc}")
        time.sleep(2)
else:
    sys.exit("database did not become available")
PY

python manage.py migrate --noinput
python manage.py sync_roles

exec "$@"
