# Copyright (c) Meta Platforms, Inc. and affiliates.
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""PytestCorpusSuite suite adapter."""

import os
import re

from ..utils.pytest import PLUSFILE_RE, target_tests
from .pytest import PytestSuite

class PytestCorpusSuite(PytestSuite):
    """pytest, for a repo whose regressions are **data files driven by one parametrised
    test module** rather than ``def test_…`` functions.

    This is a common shape once a project's product is a compiler or an analyser: pylint's
    ``tests/functional/`` is a tree of ``.py`` inputs whose expected diagnostics are
    comments inside them, collected by a single driver that parametrises over the
    directory. Adding a regression means adding a data file and nothing else.

    :class:`PytestSuite` cannot address those. It would hand the data file to pytest as if
    it were a test module, pytest would collect nothing from it, and the subtask would
    read as *not failing* pre-gold — a silent miss, not an error. So this suite maps a
    corpus file to two things instead:

    - the **driver** module, which is what pytest is actually given to run, and
    - the case's **stem** (the file name without its extension), which is the parametrised
      id, so ``-k`` narrows the driver's whole corpus down to the case that moved.

    A patch that touches ordinary test modules as well is handled by both halves at once:
    the modules are run directly and the corpus cases through the driver.

    ``corpus_re`` is what counts as corpus data and ``driver`` is the module that runs it.
    A repo with more than one corpus passes a list of ``(regex, driver)`` pairs.
    """

    no_targets = "test patch touched no .py test file and no corpus case"

    def __init__(self, corpora):
        # Accept the single-corpus form as well as the list, since most repos have one.
        if isinstance(corpora, tuple):
            corpora = [corpora]
        self.corpora = [(re.compile(pattern), driver) for pattern, driver in corpora]

    def _driver_of(self, path):
        for pattern, driver in self.corpora:
            if pattern.match(path):
                return driver
        return None

    @staticmethod
    def _stem(path):
        return os.path.splitext(os.path.basename(path))[0]

    def targets(self, diff, env=None):
        del env
        files, names = target_tests(diff)
        drivers = []
        stems = []
        for path in PLUSFILE_RE.findall(diff):
            if path == "/dev/null":
                continue
            driver = self._driver_of(path)
            if driver is None:
                continue
            if driver not in drivers:
                drivers.append(driver)
            stems.append(self._stem(path))
            # The data file is not a test module: pytest collects nothing from it, and
            # handing it over would dilute the run with an empty file.
            if path in files:
                files.remove(path)
        return sorted(set(files + drivers)), sorted(set(names + stems))
