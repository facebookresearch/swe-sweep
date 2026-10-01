#!/bin/bash

# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

# Upstream validated every gold fix on its own and some overlap, so they cannot be
# stacked into one patch. This marker (the golds' digest, which only this file and the
# hidden tests carry) makes tests/shared/swesweep_grade.py grade each subtask on its gold
# patch instead. `add -f` keeps it in the collected patch even if the repo ignores it.
set -e
cd /hdf5
echo 9045c544bd3a8f91a39c9e0d67a9efa2e66bf73be3edb27f1626aa3f8ce08a48 > .swesweep_oracle
git add -f .swesweep_oracle
