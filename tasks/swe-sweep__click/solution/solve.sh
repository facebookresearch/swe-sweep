#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /click
echo cf7e23ac8c006a55ff68896bdbec7cbf0b53ff6a79010bbb59f521b07877e4d2 > .swesweep_oracle
git add -f .swesweep_oracle
