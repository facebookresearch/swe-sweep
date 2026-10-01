#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /tokio
echo c631dbff21c2064a813b3d8dbbce3e3e8297d08ced2e4310229b9cfb0c87a50c > .swesweep_oracle
git add -f .swesweep_oracle
