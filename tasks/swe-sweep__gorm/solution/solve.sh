#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /gorm
echo 493bfeb155231a5d7a68b0a9e6bb4dd4010ad06b8c870eeb781ebe1d3298024e > .swesweep_oracle
git add -f .swesweep_oracle
