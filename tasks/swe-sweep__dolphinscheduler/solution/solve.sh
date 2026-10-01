#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /dolphinscheduler
echo 38c6f78cd1a03ffd646bd8c8d3b51aff6ac0db5140fc29ef259817a0bfcd64b3 > .swesweep_oracle
git add -f .swesweep_oracle
