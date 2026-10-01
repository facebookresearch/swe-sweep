#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /idris2
echo acd1d450c58d81cd90f080b3caacc526d9cf6a3d953a98d159277648b1100626 > .swesweep_oracle
git add -f .swesweep_oracle
