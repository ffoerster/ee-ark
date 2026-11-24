#!/usr/bin/env python3
"""Generate a requirements.txt from poetry.lock (main dependencies only).

Poetry >= 2.0 no longer ships `poetry export`; it lives in the
`poetry-plugin-export` plugin, which cannot be installed for Homebrew's
poetry. This script produces the same result for the main group so that the
Dockerfile and the safety scan use exactly the versions from the lock file.

Usage:
    python3 scripts/lock_to_requirements.py > requirements.txt
    make requirements
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "poetry.lock"

HEADER = """\
# Generated from poetry.lock - do not edit by hand.
# Regenerate with: make requirements
#
"""


def main() -> int:
    lock = tomllib.loads(LOCK.read_text(encoding="utf-8"))

    lines: list[str] = []
    for package in lock.get("package", []):
        if "main" not in package.get("groups", []):
            continue
        if package.get("optional"):
            continue

        # `markers` hold the environment conditions of the dependency
        # (e.g. `sys_platform == "win32"`); pip understands them as-is.
        # Optional extras (`extra == "ui"`) are not part of the main install.
        marker = package.get("markers") or ""
        if "extra ==" in marker:
            continue

        requirement = f"{package['name']}=={package['version']}"
        if marker:
            requirement += f" ; {marker}"
        lines.append(requirement)

    sys.stdout.write(HEADER + "\n".join(sorted(lines, key=str.lower)) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
