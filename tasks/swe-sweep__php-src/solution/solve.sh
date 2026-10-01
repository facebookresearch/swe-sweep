#!/bin/bash
# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /php-src
echo c8028092b521bead27a9e1db55755eb67d860f304ae72c6002818b514d603651 > .swesweep_oracle
git add -f .swesweep_oracle
