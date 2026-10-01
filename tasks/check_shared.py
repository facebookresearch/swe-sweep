#!/usr/bin/env python3
"""Check that every file under tests/shared/ has the same bytes in every task that ships it.

Usage: python3 check_shared.py [dataset_dir]   (default: the directory of this script)
Prints the differing files and exits 1 when the tasks disagree; meant for the release
repository's CI. Stdlib only.
"""

import hashlib
import sys
from pathlib import Path


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent
    tasks = sorted(p for p in root.iterdir() if (p / "tests" / "shared").is_dir())
    first: dict[str, tuple[str, str]] = {}
    mismatches: list[str] = []
    for task in tasks:
        shared = task / "tests" / "shared"
        for path in sorted(p for p in shared.rglob("*") if p.is_file()):
            rel = path.relative_to(shared).as_posix()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if rel not in first:
                first[rel] = (task.name, digest)
            elif first[rel][1] != digest:
                mismatches.append(f"{rel}: {task.name} != {first[rel][0]}")
    print(f"{len(tasks)} tasks, {len(first)} shared files")
    if mismatches:
        print("tests/shared/ differs across tasks:")
        print("\n".join(mismatches))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
