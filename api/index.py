"""Vercel serverless entrypoint (docs/adr/0037).

Vercel's Python runtime (@vercel/python) detects a WSGI callable named
``app`` in a file under ``api/`` and routes requests to it — see
``vercel.json``. This is a thin adapter, not a parallel entrypoint: it
defers immediately to the same WSGI application Docker/local deployments
use (``config/wsgi.py``), so there is exactly one place Django app wiring
lives.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# The repo root (parent of api/) isn't on sys.path by default in the
# function's execution environment.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

from config.wsgi import application as app  # noqa: F401
