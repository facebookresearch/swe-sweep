#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /cvc5
echo d4d5840e1bdf9f0c4877d54613a8cef9916e7b07fa18d5e2ad06f4756cd805bf > .swesweep_oracle
git add -f .swesweep_oracle
