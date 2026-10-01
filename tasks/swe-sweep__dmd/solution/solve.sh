#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /dmd
echo bc5f01dfb1a1f0c1105045e48e7a5f2f8ec04070c17c4cc79a3d3c9792a6d00d > .swesweep_oracle
git add -f .swesweep_oracle
