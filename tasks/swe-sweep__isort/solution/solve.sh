#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /isort
echo 92903eae8b7d861099042a2b6031c99313a92379d16d851a576dbfb88546e22f > .swesweep_oracle
git add -f .swesweep_oracle
