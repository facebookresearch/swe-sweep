#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /godot
echo 42cea3e84adede403be32d16216532455295338045ffc29535bc2afdb0292274 > .swesweep_oracle
git add -f .swesweep_oracle
