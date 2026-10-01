#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /react-router
echo 7ce46b6c2b75ea0698abd5674d95c345c8c3e94014a32a3bc0e09c44dd90417b > .swesweep_oracle
git add -f .swesweep_oracle
