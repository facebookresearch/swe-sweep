#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /repo
echo f4b657feb77676804e42134ba4d6dd20e69d297d05b695307879415215263aa2 > .swesweep_oracle
git add -f .swesweep_oracle
