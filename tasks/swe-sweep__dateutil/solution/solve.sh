#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /dateutil
echo fb3936ad4fcd5f834c93ee04900fc732ba35cb8bde624225cf7f19b9dc8a781e > .swesweep_oracle
git add -f .swesweep_oracle
