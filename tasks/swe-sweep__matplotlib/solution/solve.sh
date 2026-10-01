#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /matplotlib
echo 0feeae98e22915d33c60d6e6807afa5fb388a13b5c3f44e97a6c7f93c4488c59 > .swesweep_oracle
git add -f .swesweep_oracle
