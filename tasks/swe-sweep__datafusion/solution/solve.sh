#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /repo
echo 4e558c34d7028d30f1ac3ffcc5915884f5829e98443aca24866fe2a569b89a78 > .swesweep_oracle
git add -f .swesweep_oracle
