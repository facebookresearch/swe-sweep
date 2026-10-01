#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /arrow
echo 8d50d5f0d7af62677a39acc01f4a650c16bb0158ba11e89f21df7e7973a92c6a > .swesweep_oracle
git add -f .swesweep_oracle
