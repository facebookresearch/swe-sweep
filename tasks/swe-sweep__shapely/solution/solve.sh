#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /shapely
echo 985ba573516f350a234f9c4979a92001640dfd36c40952f630c6a96f3a4e67c5 > .swesweep_oracle
git add -f .swesweep_oracle
