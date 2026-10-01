#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /distributions
echo 9e4f29814e5a1f5a762f638ee500298e2961e348d1ea7070e0748996a757a104 > .swesweep_oracle
git add -f .swesweep_oracle
