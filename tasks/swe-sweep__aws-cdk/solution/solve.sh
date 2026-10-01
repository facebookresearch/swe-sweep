#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /aws-cdk
echo 498814a501f2d1845f7053781e402c59b60aafb2ef4125aec2df9b1cd39c7b6e > .swesweep_oracle
git add -f .swesweep_oracle
