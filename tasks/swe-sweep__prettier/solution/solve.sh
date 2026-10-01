#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /prettier
echo 938de41afe093090af1198522595439f361c776a620eee66a969c9d8cbfa4f33 > .swesweep_oracle
git add -f .swesweep_oracle
