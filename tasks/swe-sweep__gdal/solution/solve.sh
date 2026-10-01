#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /gdal
echo 8cf3abbd4ce160e29b2a1ad5851efe3f63229a7c5d88a58126ff78dee4c33e8b > .swesweep_oracle
git add -f .swesweep_oracle
