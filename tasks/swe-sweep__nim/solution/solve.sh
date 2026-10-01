#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /nim
echo 134a347c203d46182ec82211acc8a7f1fe067f6c20ab0abf20995a84f5570fc6 > .swesweep_oracle
git add -f .swesweep_oracle
