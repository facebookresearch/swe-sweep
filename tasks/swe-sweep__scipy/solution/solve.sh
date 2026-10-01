#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /scipy
echo 5979c3a9fb6fc8bcefd1242cb6b00576ba49e441b83d3ee00ba67c31f21c2b56 > .swesweep_oracle
git add -f .swesweep_oracle
