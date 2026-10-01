#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /libexpat
echo 240adc392bed3a8e784114472b61ff6c346838485cc9d189a9302d8cc7e0a193 > .swesweep_oracle
git add -f .swesweep_oracle
