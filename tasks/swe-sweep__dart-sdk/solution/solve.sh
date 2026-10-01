#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /dart/sdk
echo 4be6dec1bc33fbc3790e11c75c7a896ba877502d72af1d420241d06c96704b3e > .swesweep_oracle
git add -f .swesweep_oracle
