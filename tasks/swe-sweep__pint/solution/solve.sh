#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /pint
echo 5c0b82458a21d45b5bf577e6da75bb96e17aeca90640e595894f084fdfba3133 > .swesweep_oracle
git add -f .swesweep_oracle
