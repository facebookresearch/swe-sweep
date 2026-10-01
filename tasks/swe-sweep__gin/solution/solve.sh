#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /gin
echo d2894a9fbe85925bc71ef6a83a3a3c9cb708a84beec8888e128e555b72a6e67f > .swesweep_oracle
git add -f .swesweep_oracle
