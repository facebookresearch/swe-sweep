#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /z3
echo 9992b802955ead597a1f1e39ea5d22e82060373d1353d03c3099751fa6d41302 > .swesweep_oracle
git add -f .swesweep_oracle
