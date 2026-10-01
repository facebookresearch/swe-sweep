#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /terser
echo ea628a22ecd05871e019d01375d3d2a2fe148a25266474d419d5a028ae3796f1 > .swesweep_oracle
git add -f .swesweep_oracle
