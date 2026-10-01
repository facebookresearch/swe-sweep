#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /nacos
echo 84d3ed757934f52f8c207070b2ad1736fc355b9ccc17d599decf255bfd48aadc > .swesweep_oracle
git add -f .swesweep_oracle
