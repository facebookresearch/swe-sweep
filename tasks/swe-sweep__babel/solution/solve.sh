#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /babel
echo 2a15acc9f17aacd3fc3f80ab7102d30f7cf853d961b5a27c5eaefea925092008 > .swesweep_oracle
git add -f .swesweep_oracle
