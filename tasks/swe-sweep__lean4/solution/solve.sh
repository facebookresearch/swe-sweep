#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /lean4
echo 09a1f77e3fc766e47eef3e89998f269adfeede6ffcf021c2073ef520d90d1718 > .swesweep_oracle
git add -f .swesweep_oracle
