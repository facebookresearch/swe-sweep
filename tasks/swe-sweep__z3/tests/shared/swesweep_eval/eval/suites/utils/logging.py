# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Minimal stderr logging used while suite output is being captured."""

import sys


def log(*values: object) -> None:
    print(*values, file=sys.stderr)
    sys.stderr.flush()
