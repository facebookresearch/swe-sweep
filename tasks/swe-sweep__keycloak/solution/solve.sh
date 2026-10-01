#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /keycloak
echo 40ce98104ed2039ae527c72d92553a84bfda56e010f32272aa3c2b8f6ebdec3a > .swesweep_oracle
git add -f .swesweep_oracle
