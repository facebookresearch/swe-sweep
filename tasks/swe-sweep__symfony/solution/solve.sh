#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /symfony
echo a7299589626473dee112cd79e93785a7a1aa5763f6a831d0901ce233c24433c6 > .swesweep_oracle
git add -f .swesweep_oracle
