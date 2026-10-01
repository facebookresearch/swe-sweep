#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /formulajs
echo 3daa64b209d3b881e15b02ae1089f078a488df40dece8c9b519ce7078017daaa > .swesweep_oracle
git add -f .swesweep_oracle
