#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /echo
echo 014f14d6910fe9b08939860e19cf46de2a3bec70566cb1b71f8fd33f5a77b5ce > .swesweep_oracle
git add -f .swesweep_oracle
