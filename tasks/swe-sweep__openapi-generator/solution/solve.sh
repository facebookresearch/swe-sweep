#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /openapi-generator
echo 90829de2bf734577b8158c382a34cf29d251eeabc24661ce33ef722cac86a4f5 > .swesweep_oracle
git add -f .swesweep_oracle
