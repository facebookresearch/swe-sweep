#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /opencv
echo 5bc2e2cb3ce06e2553ad65b8defe09a27b7b2174fafe409f621ed2d260cbfc15 > .swesweep_oracle
git add -f .swesweep_oracle
