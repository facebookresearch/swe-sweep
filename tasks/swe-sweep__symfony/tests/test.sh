#!/bin/bash

# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

# SWE-sweep grader: upstream's evaluator run locally (tests/shared/swesweep_grade.py).
# /logs/verifier/{reward.json,eval.json,eval_output.json}. The verifier image
# (tests/Dockerfile) ships the interpreter under /opt/swesweep; a shared-container run
# (the agent's image) falls back to a python3 >= 3.11 on PATH.
set -u
mkdir -p /logs/verifier
# Some sandbox runtimes start with a 1024 open-files soft limit (docker's default is
# ~1M); black's blackd suite fails with EMFILE below it.
ulimit -n "$(ulimit -Hn)" 2>/dev/null || true
PY=/opt/swesweep/python/bin/python3
# Only the verifier image (tests/Dockerfile) has this interpreter: tell the grader it is
# in a verifier sandbox, where a missing patch is a harness failure, not an empty diff.
if [ -x "$PY" ]; then export SWESWEEP_VERIFIER_IMAGE=1; fi
if [ ! -x "$PY" ]; then
  PY=""
  for cand in python3 python3.13 python3.12 python3.11 python; do
    if command -v "$cand" >/dev/null 2>&1 \
        && "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
      PY="$(command -v "$cand")"
      break
    fi
  done
fi
if [ -z "$PY" ]; then
  echo "swesweep: no python3 >= 3.11 in this container; grade in the tests/Dockerfile verifier image (environment_mode = \"separate\")" >&2
  printf '{"reward": 0.0, "grader_failed": 1.0}\n' > /logs/verifier/reward.json
  exit 1
fi
exec "$PY" /tests/shared/swesweep_grade.py
