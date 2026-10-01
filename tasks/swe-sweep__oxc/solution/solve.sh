#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /repo
echo 105b4ba2ed6d062d554d6aa3b11cb929c96052242bad9113f1235b647f5b6e73 > .swesweep_oracle
git add -f .swesweep_oracle
