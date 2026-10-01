#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /gson
echo 419987bd315f66014b06889bff30af79305c9f3cc836d0a954711e121dd7b3bf > .swesweep_oracle
git add -f .swesweep_oracle
