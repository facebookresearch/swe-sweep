#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /networkx
echo 819d9b4c8b439630a70e506776cc90d4b85814b51ccd764c93418347282712e9 > .swesweep_oracle
git add -f .swesweep_oracle
