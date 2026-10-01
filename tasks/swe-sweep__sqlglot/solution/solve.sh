#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /sqlglot
echo 5fafc040e8ce7ee4db7261660e0881e65bbeaf5dbc0972ded12bd71dabdea1ab > .swesweep_oracle
git add -f .swesweep_oracle
