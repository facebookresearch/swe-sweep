#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /optuna
echo c7f98a5b0c8b0a04db81641850261f4d58608a9dde4d39e7f6e65ca2aa5a0048 > .swesweep_oracle
git add -f .swesweep_oracle
