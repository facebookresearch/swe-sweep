#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /elixir
echo 67d76eddb490ffed3678db6802f8311351c80cde23cf73db4e7ef77ad03332cc > .swesweep_oracle
git add -f .swesweep_oracle
