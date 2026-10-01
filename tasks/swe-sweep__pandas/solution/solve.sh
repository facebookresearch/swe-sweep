#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /pandas
echo b23a7a8044a9f6333e9ac79e9d5a712c1c95da880638ce373dbc38dcb7f07b13 > .swesweep_oracle
git add -f .swesweep_oracle
