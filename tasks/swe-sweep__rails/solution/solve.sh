#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /rails
echo 1998f631828e4b270ba5032de4ce78f4b4f583afeddef1b182a846d68d71db9c > .swesweep_oracle
git add -f .swesweep_oracle
