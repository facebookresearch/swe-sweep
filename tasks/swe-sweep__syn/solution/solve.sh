#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /syn
echo e2ebc20615c5f0cf1e49101a64f1a961853e87812658371aa2e6d00b1a94ce25 > .swesweep_oracle
git add -f .swesweep_oracle
