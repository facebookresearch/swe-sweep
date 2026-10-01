#!/usr/bin/env python3

# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Shared constants for Ruby and PHP suite adapters."""
import json
import os
import re

from swesweep_eval.eval.suites.utils.compiled import _parse_junit, _patched_files, _run
from swesweep_eval.eval.suites.utils.logging import log

# --- rspec ----------------------------------------------------------------------

_SPEC_SUFFIX = "_spec.rb"

# An example the patch ADDS. RSpec spells one four ways (`it`, `specify`, `example`,
# `scenario`) and takes its description as the first argument, quoted either way, with or
# without parentheses. A bare `it { is_expected.to eq 1 }` has no description at all and
# is deliberately not matched — there is nothing to filter on, and the file-level fallback
# covers it.
_RSPEC_DECL_RE = re.compile(r"^\+\s*(?:it|specify|example|scenario)\s*\(?\s*(['\"])(?P<desc>.+?)\1")
# An example the patch EDITS: git puts the enclosing block in the hunk header, which is
# the only place an unchanged `it '...'` shows up in the diff. Without it, a patch that
# only strengthens an existing example has no name to narrow to. The pytest and gtest
# suites read their enclosing declaration from the hunk header the same way.
_RSPEC_HUNK_RE = re.compile(r"^@@ .*@@.*\b(?:it|specify|example|scenario)\s*\(?\s*(['\"])(?P<desc>.+?)\1")
# An interpolated description (`it "handles #{x}"`) cannot be matched literally, and a
# `-e` on the part before the interpolation would silently widen the selection.
_RSPEC_INTERP_RE = re.compile(r"#\{")

_RSPEC_JSON = "/tmp/rspec.json"
_RSPEC_STATUS = {"passed": "passed", "failed": "failed", "pending": "skipped"}




# --- phpunit --------------------------------------------------------------------

# A test method the patch ADDS. PHPUnit takes a method as a test if it is named `test*`,
# or if it is annotated `@test` / `#[Test]`; only the name is matched here, and the
# annotated form is picked up through the arming pass below.
_PHP_TEST_METHOD_RE = re.compile(r"^\+\s*(?:public\s+|protected\s+|private\s+)?(?:static\s+)?function\s+(test\w*)\s*\(")
_PHP_ANY_METHOD_RE = re.compile(r"^\+\s*(?:public\s+|protected\s+|private\s+)?(?:static\s+)?function\s+(\w+)\s*\(")
_PHP_TEST_ANNOT_RE = re.compile(r"^\+\s*(?:/\*\*|\*|//)?\s*(?:@test\b|#\[\s*Test\s*[]\(])")
# A method the patch EDITS: the enclosing signature comes back in the hunk header.
_PHP_HUNK_RE = re.compile(r"^@@ .*@@.*\bfunction\s+(test\w*)\s*\(")

_PHPUNIT_XML = "/tmp/phpunit.xml"
