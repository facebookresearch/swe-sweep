#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /svgo
echo 2c3e9b350841e3caf5ffced745ca535cfdcdb8416717e90ceb5e81535da43696 > .swesweep_oracle
git add -f .swesweep_oracle
