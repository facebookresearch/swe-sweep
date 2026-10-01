#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /dayjs
echo 66d21ecafdc20ff1aba8997ae6031c6c95e5ae86f5b4aa5b3a2fd31f7bb7f943 > .swesweep_oracle
git add -f .swesweep_oracle
