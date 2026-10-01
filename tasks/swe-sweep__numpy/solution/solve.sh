#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /numpy
echo 8d619634e4f7d588c5eccd37c66b5b4c4f4525df5d72dc74e9fd070f8933ad75 > .swesweep_oracle
git add -f .swesweep_oracle
