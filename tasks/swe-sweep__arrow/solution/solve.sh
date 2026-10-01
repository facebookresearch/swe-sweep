#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /arrow
echo b076d58a7d80ff906246b3fe5161bd0a66691ae9480d7abb5714a9b000fdb781 > .swesweep_oracle
git add -f .swesweep_oracle
