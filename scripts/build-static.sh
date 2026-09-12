#!/usr/bin/env bash
set -euo pipefail

echo "==> Fetching Tailwind"
bash scripts/fetch-tailwind.sh

echo "==> Building Tailwind CSS"
./bin/tailwindcss \
  -i static/src/app.css \
  -o static/css/app.css \
  --minify

echo "==> Verifying generated CSS"

if [ ! -f static/css/app.css ]; then
    echo "ERROR: static/css/app.css was not generated."
    exit 1
fi

if [ ! -s static/css/app.css ]; then
    echo "ERROR: static/css/app.css is empty."
    exit 1
fi

echo "Generated CSS:"
ls -lh static/css/app.css

echo "==> Collecting Django static files"

rm -rf staticfiles

python manage.py collectstatic --noinput

echo "==> Verifying WhiteNoise manifest"

python - <<'PY'
import json
import sys
from pathlib import Path

manifest_path = Path("staticfiles/staticfiles.json")

if not manifest_path.exists():
    print("ERROR: staticfiles/staticfiles.json was not generated.")
    sys.exit(1)

with manifest_path.open(encoding="utf-8") as f:
    manifest = json.load(f)

paths = manifest.get("paths", {})

if "css/app.css" not in paths:
    print("ERROR: css/app.css is missing from the Django staticfiles manifest.")
    print("Manifest entries:")
    for key in sorted(paths):
        print(f"  {key}")
    sys.exit(1)

print("OK: css/app.css exists in staticfiles manifest.")
print(f"Manifest entry: {paths['css/app.css']}")
PY

echo "==> Static build completed successfully"