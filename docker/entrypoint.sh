#!/usr/bin/env sh
# Container bootstrap: migrate -> seed (first boot only) -> collect static -> exec.
set -e

echo "[entrypoint] waiting for the database..."
attempts=0
until python - <<'PY'
import os, sys
from urllib.parse import urlparse
url = os.getenv("DATABASE_URL", "")
if not url:
    sys.exit(0)
import psycopg
parsed = urlparse(url)
try:
    with psycopg.connect(
        dbname=parsed.path.lstrip("/"),
        user=parsed.username or "",
        password=parsed.password or "",
        host=parsed.hostname or "localhost",
        port=parsed.port or 5432,
        connect_timeout=3,
    ):
        pass
except Exception as exc:  # pragma: no cover - startup race
    print(f"  ... {exc}")
    sys.exit(1)
PY
do
  attempts=$((attempts + 1))
  if [ "$attempts" -ge 30 ]; then
    echo "[entrypoint] database never became reachable" >&2
    exit 1
  fi
  sleep 2
done

echo "[entrypoint] applying migrations"
python manage.py migrate --noinput

if [ "${SEED_DEMO_DATA:-1}" = "1" ]; then
  echo "[entrypoint] seeding the demo catalogue if the database is empty"
  python manage.py shell -c "
from store.models import Product
if not Product.objects.exists():
    from django.core.management import call_command
    call_command('seed_store')
else:
    print('catalogue already present - skipping seed')
"
fi

echo "[entrypoint] collecting static files"
python manage.py collectstatic --noinput --clear >/dev/null

echo "[entrypoint] starting: $*"
exec "$@"
