#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /testify
echo 8347e6798b2a3ab0490516e76d649116df12346bcc20ca74ecc7c1d9d0903e75 > .swesweep_oracle
git add -f .swesweep_oracle
