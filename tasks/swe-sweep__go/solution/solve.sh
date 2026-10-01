#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /go
echo 7be811ba0f12010d4b00eec920ef7cec26232c5c5c41bd6b819142874b4a8cdf > .swesweep_oracle
git add -f .swesweep_oracle
