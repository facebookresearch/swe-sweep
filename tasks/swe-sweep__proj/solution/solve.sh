#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /proj
echo c3b197971a3f27ed42c78599c823401cfefd9c26e23bcb6e227e324d68dd0965 > .swesweep_oracle
git add -f .swesweep_oracle
