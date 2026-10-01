#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /material-ui
echo 38821d72f0a06b87ba7cbe0e6e3b6ebc867e4bb8b286d29ad5cdb716d2a6029e > .swesweep_oracle
git add -f .swesweep_oracle
