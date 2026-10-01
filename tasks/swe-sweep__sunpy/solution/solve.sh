#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /sunpy
echo 9e4235e330f2b599e46489f964b1c50f0d68ab7152aad69b94dc24d3c5cd6dc2 > .swesweep_oracle
git add -f .swesweep_oracle
