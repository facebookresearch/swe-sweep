#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /rxjava
echo 444a0c108812f3179f1d5621a64402adbcb89fec4d53071517c1957919e3ee73 > .swesweep_oracle
git add -f .swesweep_oracle
