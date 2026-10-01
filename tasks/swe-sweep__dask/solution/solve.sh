#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /dask
echo 830d74c40fef3ce165322f5a5600933e131ebbe2f2802873c99e06ba8638c63c > .swesweep_oracle
git add -f .swesweep_oracle
