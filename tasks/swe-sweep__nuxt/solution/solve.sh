#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /nuxt
echo 68b723abadd09e47240dea376482541edb0f4d9b169676ca67f1aa3e59e6b67e > .swesweep_oracle
git add -f .swesweep_oracle
