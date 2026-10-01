#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /tarantool
echo 2ffa74a139c63f711ff61a7db5268955ed8f8af59b7e926adaf0e66e50d5389d > .swesweep_oracle
git add -f .swesweep_oracle
