#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /jest
echo f819250c9bd567fd0c6b112fc3fa1e2b083b5d4973fa082a4c1ceb2f149a1732 > .swesweep_oracle
git add -f .swesweep_oracle
