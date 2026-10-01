#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /qutip
echo a8244e2d3fb3a6468fb27622b8f3156de13f14fd01036e9768bbeeda74a20d26 > .swesweep_oracle
git add -f .swesweep_oracle
