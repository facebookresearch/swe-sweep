#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /black
echo 0ed5bd19abb5a57c08ac72af7711e5fe867ee3887fbd9b865417913fc5c8df0c > .swesweep_oracle
git add -f .swesweep_oracle
