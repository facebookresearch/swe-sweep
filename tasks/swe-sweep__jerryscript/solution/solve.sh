#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /jerryscript
echo ad0eef51febc38708df5239152c91d6040b9034c97da069632cf1f01dfc9e5a4 > .swesweep_oracle
git add -f .swesweep_oracle
