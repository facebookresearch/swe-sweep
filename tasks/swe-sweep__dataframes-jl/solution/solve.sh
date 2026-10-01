#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /dataframes
echo 9600669dc6361241c467f9a6799fff362115f989093b88b97af722179dc9cab7 > .swesweep_oracle
git add -f .swesweep_oracle
