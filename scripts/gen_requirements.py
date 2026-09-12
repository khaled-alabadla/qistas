#!/usr/bin/env python
"""Generate requirements.txt from pyproject.toml's runtime dependencies.

Vercel's Python builder (@vercel/python) resolves dependencies from
requirements.txt, not pyproject.toml (docs/adr/0037). This script is the
single source of truth's *reader*, not a second source of truth: edit
dependencies in pyproject.toml, then re-run this script before deploying.

    python scripts/gen_requirements.py
"""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    deps = pyproject["project"]["dependencies"]
    header = (
        "# Generated from pyproject.toml by scripts/gen_requirements.py — do not\n"
        "# hand-edit. Re-run the script after changing [project.dependencies].\n"
        "# Consumed by Vercel's Python builder (docs/adr/0037); Docker/local\n"
        '# installs still use `pip install -e ".[dev]"` from pyproject.toml.\n'
    )
    out = ROOT / "requirements.txt"
    out.write_text(header + "\n".join(deps) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(deps)} packages)")  # noqa: T201 — CLI status output


if __name__ == "__main__":
    main()
