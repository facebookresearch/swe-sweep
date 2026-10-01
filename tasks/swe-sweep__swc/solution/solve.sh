#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /swc
echo 8d840e818b53a485fea0259c9053d1e12068e82511e7d4a6dcd51bdc921a6ab6 > .swesweep_oracle
git add -f .swesweep_oracle
