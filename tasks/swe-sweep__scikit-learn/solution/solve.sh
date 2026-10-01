#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /scikit-learn
echo e7eaa5c0ae474769a38a1cda0fad8f3b041947d357ffd33a112d09130dc3fc83 > .swesweep_oracle
git add -f .swesweep_oracle
