#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /pendulum
echo 47e67973997b43f81d0f9b3e7334eedd3b16816f5f897b867a17feb5b5dffd2a > .swesweep_oracle
git add -f .swesweep_oracle
