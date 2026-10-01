#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /ruff
echo 9ad389bc636535eb51813909f097702d72261f7b8624ba55bd71e9d5b1aad45e > .swesweep_oracle
git add -f .swesweep_oracle
