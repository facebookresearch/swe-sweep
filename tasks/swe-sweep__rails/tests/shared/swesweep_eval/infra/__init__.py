# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Infrastructure layer — the "hard" compute/storage/registry plumbing with a clear
Python interface, kept out of the CLI (``cli/`` is only typer shells + orchestration glue).

- ``infra.container_session`` — the small persistent-container interface for evaluation.
- ``infra.aws`` — the AWS Batch census fan-out (config / batch / ecr) plus the S3 ``data/`` sync.
- ``infra.meta`` — Meta-internal vmvm image storage and the Manifold S3 backup.
- ``infra.plan`` — the pure rank sharding both the submit side and the workers use.

``infra.aws``'s ``__init__`` re-exports its public API, so callers do
``from swesweep_eval.infra import aws`` and use ``aws.submit_jobs(...)`` etc.
"""

from __future__ import annotations
