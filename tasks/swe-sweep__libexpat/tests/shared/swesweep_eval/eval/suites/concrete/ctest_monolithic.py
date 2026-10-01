"""CTestMonolithicSuite suite adapter."""

from ..utils.compiled import _CTEST_EXTS, _patched_files
from .ctest_data import CTestDataSuite

class CTestMonolithicSuite(CTestDataSuite):
    """CTest over a **single test program** that every test source compiles into.

    Keyed on the framework, like every other suite here: the framework is "one hand-rolled
    harness, one binary, registered with CMake as one (or a couple of) ``add_test`` cases".
    libexpat is the shape — ``expat/tests/{basic,ns,misc,alloc,...}_tests.c`` all link into
    ``runtests`` (and its C++ twin ``runtests_cxx``), and ``expat_add_test`` registers the
    *binaries*, not the cases inside them.

    Neither :class:`CTestSuite` nor :class:`CTestDataSuite` can express that.
    ``CTestSuite`` reads the case id off the patched file's basename, which here resolves
    to a target that does not exist; ``CTestDataSuite`` reads it off the path, which here
    is the same id for every file. So this suite reads it off **nothing**: any patched file
    under ``test_dirs`` selects the fixed ``names``.

    The consequence is deliberate and worth stating: the grading granularity is the whole
    binary. ``fails_pre_gold`` means "the test program fails", not "this case fails". That
    is a sound fail->pass signal only if the program is green on the pristine image, which
    is the base-image invariant anyway — but it also means a single unrelated flaky case
    takes every subtask of the task down with it, so it is worth re-checking after any
    change to the image.

    A crashed binary reads as a failing test for free: CTest reports the case as failed
    when the process dies, whatever the harness did or did not print.
    """

    no_targets = "test patch touched no source of the monolithic CTest test program"

    def __init__(self, build_dir="/build", test_dirs=("expat/tests",),
                 names=("runtests",), all_target="all", exts=_CTEST_EXTS, source_subdir=""):
        # `all_target` is what gets built for *any* selection, because there is only ever
        # the one program. "all" is the safe default: a repo with a monolithic runner
        # rarely bothers to give it an aggregate target of its own, and the extra work is
        # incremental against the image's warm build tree.
        super().__init__(build_dir=build_dir, corpus_dir=".", all_target=all_target,
                         source_subdir=source_subdir)
        self.test_dirs = tuple(d.rstrip("/") for d in test_dirs)
        self.names = tuple(names)
        self.exts = tuple(exts)

    def targets(self, diff, env=None):
        del env
        """``(files, names)`` — the patched test sources, and the fixed program ids.

        ``files`` is only evidence that the patch touched this suite at all; the selector
        never depends on it.
        """
        files = []
        for path in _patched_files(diff):
            if not path.lower().endswith(self.exts):
                continue
            if any(path == d or path.startswith(d + "/") for d in self.test_dirs):
                files.append(path)
        if not files:
            return [], []
        return sorted(set(files)), sorted(self.names)
