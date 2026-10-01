#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /fsharp
echo 3526ae87e4b9622776ab52c3809a61a3050016e6ddd9209e340ec2e601fbff50 > .swesweep_oracle
git add -f .swesweep_oracle
