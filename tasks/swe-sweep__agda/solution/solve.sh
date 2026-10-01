#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /agda
echo 7136c6d164de2cba601b77aca07de21a0005317a707ee276202a706b817de504 > .swesweep_oracle
git add -f .swesweep_oracle
