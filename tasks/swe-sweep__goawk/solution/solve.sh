#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /goawk
echo e0c3fdffac770c84a5671823b02274f8fefba902d788ccafa1a54dd9cf29f1ee > .swesweep_oracle
git add -f .swesweep_oracle
