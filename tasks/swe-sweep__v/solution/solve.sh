#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /v
echo 04d8a8e210a9b9e291a4e3a63250e23bb13b7937d94dc1b45151a086f7c82272 > .swesweep_oracle
git add -f .swesweep_oracle
