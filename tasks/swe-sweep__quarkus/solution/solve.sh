#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /quarkus
echo 53e4cf8cc206e40608516ab2246b4fc61b260a8ca0c3e3b8ac899632dbcb32f5 > .swesweep_oracle
git add -f .swesweep_oracle
