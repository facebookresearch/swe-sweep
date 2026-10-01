"""Minimal stderr logging used while suite output is being captured."""

import sys


def log(*values: object) -> None:
    print(*values, file=sys.stderr)
    sys.stderr.flush()
