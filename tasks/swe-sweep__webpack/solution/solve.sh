#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /webpack
echo e875230d05a6e7c97e88ed5858e68e1a2d2b365aa2c894ba322f28aef5961d9e > .swesweep_oracle
git add -f .swesweep_oracle
