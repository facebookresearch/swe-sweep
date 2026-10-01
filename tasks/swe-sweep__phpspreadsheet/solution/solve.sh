#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /phpspreadsheet
echo aac9e63d4e05475fb3728e94b80910fb98ef54cf2e347a0eefab5547e5f55074 > .swesweep_oracle
git add -f .swesweep_oracle
