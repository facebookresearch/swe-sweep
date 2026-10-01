"""JestCorpusSuite suite adapter."""

import os
import re

from ..utils.javascript import _added_names, _spec_files
from ..utils.pytest import PLUSFILE_RE
from .jest import JestSuite

class JestCorpusSuite(JestSuite):
    """jest over a **flat data corpus** — one file per case, named by the file itself.

    This is :class:`PytestCorpusSuite`'s shape in the JavaScript ecosystem, and it is what a
    rewriting tool's suite usually looks like: svgo keeps one ``.svg`` per plugin case in
    ``test/plugins/``, holding the input and the expected output separated by a marker, and a
    single driver spec reads the directory and emits ``it(<the file's stem>)`` for each one.

    :class:`JestSuite` cannot address those. The data file is not JavaScript, so plain
    selection returns nothing and the subtask reads as *not failing* pre-gold — a silent
    miss, not an error. :class:`JestFixtureSuite` cannot either: it names a case after a
    *directory* segment and explicitly skips a path whose case resolves to the file itself.

    So this suite maps a corpus file to two things instead:

    - the **driver** spec, which is what jest is actually given to run, and
    - the case's **stem** (the file name without its extension), which is the name the driver
      passes to ``it``, so ``-t`` narrows the driver's whole corpus to the case that moved.

    ``corpora`` is a list of ``(regex, driver)`` pairs, matched in order against the start of
    the path; a repo with one corpus may pass the pair on its own. A patch that touches
    ordinary spec files as well is handled by both halves at once.
    """

    no_targets = "test patch touched no JavaScript test file and no known data corpus"

    @classmethod
    def from_config(cls, values, *, repo, create_suite):
        del repo, create_suite
        corpora = [tuple(entry) for entry in values.pop("corpora")]
        return cls(corpora=corpora, **values)

    def __init__(self, corpora, config=None):
        JestSuite.__init__(self, config=config)
        if isinstance(corpora, tuple):
            corpora = [corpora]
        self.corpora = [(re.compile(pattern), driver) for pattern, driver in corpora]

    def _driver_of(self, path):
        for pattern, driver in self.corpora:
            if pattern.match(path):
                return driver
        return None

    def targets(self, diff, env=None):
        del env
        files = _spec_files(diff)
        names = list(_added_names(diff))
        drivers = []
        for path in PLUSFILE_RE.findall(diff):
            if path == "/dev/null":
                continue
            driver = self._driver_of(path)
            if driver is None:
                continue
            if driver not in drivers:
                drivers.append(driver)
            names.append(os.path.splitext(os.path.basename(path))[0])
            # The data file is not a spec: handing it to jest as a positional pattern only
            # risks matching an unrelated spec by substring.
            if path in files:
                files.remove(path)
        return sorted(set(files + drivers)), sorted(set(names))
