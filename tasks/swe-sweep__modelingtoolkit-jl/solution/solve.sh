#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /modelingtoolkit
echo c29721e674e7a427bd78bd30e52572aee6b10d7cf434a37132f4d94ed65693b1 > .swesweep_oracle
git add -f .swesweep_oracle
