#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /pulsar
echo 004c246b5a29b6961cc65b359779a4c89420cb4b14acf9adaf464f6ea43a91c7 > .swesweep_oracle
git add -f .swesweep_oracle
