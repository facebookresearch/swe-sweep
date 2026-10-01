#!/usr/bin/env python3
"""Bump the swe-sweep version in pyproject.toml."""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
VERSION_RE = re.compile(r'^version\s*=\s*"([^"]+)"', re.MULTILINE)


def main() -> None:
    text = PYPROJECT.read_text()
    match = VERSION_RE.search(text)
    if not match:
        print("Error: could not find version in", PYPROJECT)
        sys.exit(1)

    current = match.group(1)
    print(f"Current version: {current}")
    new = input("New version: ").strip()
    if not new:
        print("No version entered, aborting.")
        sys.exit(1)

    updated = text[: match.start(1)] + new + text[match.end(1) :]
    PYPROJECT.write_text(updated)
    print(f"Updated {PYPROJECT.relative_to(ROOT)}: {current} -> {new}")

    tag = f"v{new}"
    subprocess.run(["git", "add", str(PYPROJECT)], check=True)
    subprocess.run(["git", "commit", "-m", f"Bump version to {new}"], check=True)
    subprocess.run(["git", "tag", tag], check=True)

    print(f"\nTo push:\n  git push && git push origin {tag}")


if __name__ == "__main__":
    main()
