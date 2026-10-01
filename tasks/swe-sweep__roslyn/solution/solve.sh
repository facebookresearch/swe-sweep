#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /roslyn
echo a6477f78ee390c69f85bf3cd3782cb5f7743a49eda8aa6605908f3bd620eec44 > .swesweep_oracle
git add -f .swesweep_oracle
