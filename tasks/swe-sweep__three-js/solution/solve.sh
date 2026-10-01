#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /three.js
echo 390573b0e64418ec38195e688931e15263e527d224168181ac6919772c0a9f80 > .swesweep_oracle
git add -f .swesweep_oracle
