"""ExUnitSuite suite adapter."""

import posixpath
import subprocess

from ..base import FullSuite
from ..utils.compiled import _patched_files
from ..utils.logging import log


class ExUnitSuite(FullSuite):
    """ExUnit run the way an Elixir umbrella runs it: one application at a time.

    This is the shape of the Elixir distribution and of every umbrella project built on
    it — the repository is a directory of applications, each ``<apps_root>/<app>/{lib,
    src,test}``, and a test file is executed by the *application's own* elixir with its
    test helper required first::

        cd lib/elixir && ../../bin/elixir -r test/elixir/test_helper.exs -pr test/elixir/string_test.exs

    Two details are Elixir's own and neither is optional.

    **The helper is found, not assumed.** Most applications keep it at
    ``test/test_helper.exs``, but the standard library's suite is one level deeper
    (``test/elixir/test_helper.exs``) because ``lib/elixir/test`` also holds the Erlang
    suite. The helper is what calls ``ExUnit.start()``, so requiring the wrong one means
    no tests run at all and the file passes vacuously — so the adapter walks up from the
    test file to the application root and takes the first ``test_helper.exs`` that
    actually exists in the container.

    **The unit is the file.** ExUnit's console output names only the failures, and its
    machine-readable formatters have to be configured from inside the helper, which is
    repository code we do not get to change. The process exit status is the verdict, and
    it is an exact one: ExUnit exits non-zero iff a test in that file failed. A file that
    fails to *compile* is likewise a failing test, which for a language repository is the
    commonest pre-gold state there is.

    ``node_name`` runs a suite as a distributed node. Upstream does this for the
    standard library, whose ``Node`` tests need it — and only for it: on a named node
    the iex prompt reads ``iex(primary@host)1>`` and logger's reports carry
    ``on node :primary@host``, which those applications' own tests assert against the
    unnamed form. ``node_apps`` lists the applications the visible gate runs as a named
    node; unset, every application runs named (the historical behaviour). Targeted and
    reproduction runs keep ``node_name`` for every file, the way the hidden results were
    recorded.
    """

    no_targets = "test patch touched no ExUnit test file"

    def __init__(
        self,
        apps_root="lib",
        elixir="bin/elixir",
        test_subdir="test",
        helper="test_helper.exs",
        node_name=None,
        node_apps=None,
        eval_apps=(),
    ):
        self.apps_root = apps_root.strip("/")
        self.elixir = elixir
        self.test_subdir = test_subdir.strip("/")
        self.helper = helper
        self.node_name = node_name
        self.node_apps = None if node_apps is None else set(node_apps)
        self.eval_apps = list(eval_apps)

    # --- resolving the diff --------------------------------------------------

    def targets(self, diff, env=None):
        """``([(app, path-within-app), ...], [])``.

        ``names`` stays empty: ExUnit's ``--only``/line selectors address a *tag* or a
        line number rather than a test name, so a touched file runs whole — the same
        fallback maven and prove take.
        """
        del env
        prefix = self.apps_root + "/" if self.apps_root else ""
        found = []
        for path in _patched_files(diff):
            if prefix and not path.startswith(prefix):
                continue
            app, _, inside = path[len(prefix) :].partition("/")
            if not app or not inside.startswith(self.test_subdir + "/"):
                continue
            if not inside.endswith("_test.exs"):
                continue
            if (app, inside) not in found:
                found.append((app, inside))
        return sorted(found), []

    # --- running -------------------------------------------------------------

    def _app_dir(self, repo, app):
        return posixpath.join(repo, self.apps_root, app) if self.apps_root else posixpath.join(repo, app)

    def _driver(self):
        """The elixir driver, relative to the application directory we run from."""
        depth = len(self.apps_root.split("/")) + 1 if self.apps_root else 1
        return posixpath.join(*([".."] * depth), *self.elixir.split("/"))

    def _helper_for(self, env, repo, app, inside):
        """The nearest existing ``test_helper.exs`` above ``inside`` — see the docstring."""
        directory = posixpath.dirname(inside)
        while True:
            candidate = posixpath.join(directory, self.helper)
            if env.is_file(posixpath.join(self._app_dir(repo, app), candidate)):
                return candidate
            if directory in ("", ".", self.test_subdir):
                return None
            directory = posixpath.dirname(directory)

    def _run(self, targets, env, repo, timeout, node_name):
        outcomes = {}
        commands = []
        output = []
        returncode = 0
        for app, inside in targets:
            argv = [self._driver()]
            if node_name:
                argv += ["--sname", node_name]
            helper = self._helper_for(env, repo, app, inside)
            if helper is not None:
                argv += ["-r", helper]
            argv += ["-pr", inside]
            cwd = self._app_dir(repo, app)
            commands.append("cd %s && %s" % (cwd, " ".join(argv)))
            try:
                result = env.execute(argv, cwd=cwd, timeout=timeout, merge_stderr=True)
            except subprocess.TimeoutExpired:
                log("%s TIMEOUT after %ds" % (commands[-1], timeout))
                return outcomes, True, commands, returncode, "\n".join(output)
            log("%s rc=%d" % (commands[-1], result.returncode))
            log(result.stdout[-2500:])
            output.append(result.stdout)
            returncode = max(returncode, result.returncode)
            outcomes["%s::%s" % (app, inside)] = "passed" if result.returncode == 0 else "failed"
        return outcomes, False, commands, returncode, "\n".join(output)

    def run_tests(self, env, repo, files, names, timeout, jobs):
        del names, jobs
        outcomes, timed_out, _commands, _rc, _output = self._run(files or [], env, repo, timeout, self.node_name)
        n = len([value for value in outcomes.values() if value != "skipped"])
        return outcomes, n, False, timed_out

    # --- the visible regression gate -----------------------------------------

    def _test_files(self, env, repo, app):
        """Every ``*_test.exs`` of one application, as paths relative to the app directory.

        ``find`` rather than the shell's glob: the driver is exec'd with an argv, no
        shell expands a ``**`` for us, and the application's own listing is what the
        whole-app run would have picked up.
        """
        result = env.execute(
            ["find", self.test_subdir, "-type", "f", "-name", "*_test.exs"],
            cwd=self._app_dir(repo, app),
            merge_stderr=True,
        )
        if result.returncode != 0:
            log(
                "find %s/%s rc=%d: %s"
                % (self._app_dir(repo, app), self.test_subdir, result.returncode, result.stdout[-500:])
            )
            return []
        return sorted(line.strip() for line in result.stdout.splitlines() if line.strip())

    def run_all(self, env, repo, timeout, cap, jobs):
        """Every test file of every configured application, one run per file.

        The process exit status is ExUnit's only verdict, and one failing file fails a
        whole-application run — which would drop every sibling file in that application
        from the regression gate with it. So the visible suite runs at the granularity
        the hidden runs already use: per file, with the same ``app::test/...`` ids, the
        same helper resolution and the same driver command as ``_run``. A file that
        cannot pass standalone on the pristine tree belongs on the task's ignore list,
        not in the gate.
        """
        del jobs
        outcomes = {}
        commands = []
        output = []
        returncode = 0
        for app in self.eval_apps:
            node_name = (
                self.node_name
                if self.node_apps is None or app in self.node_apps
                else None
            )
            files = self._test_files(env, repo, app)
            app_outcomes, timed_out, app_commands, app_rc, app_output = self._run(
                [(app, inside) for inside in files], env, repo, timeout, node_name
            )
            outcomes.update(app_outcomes)
            commands.extend(app_commands)
            output.append(app_output)
            returncode = max(returncode, app_rc)
            if timed_out:
                return None, True, self._capture(commands, returncode, "\n".join(output), cap)
        return outcomes, False, self._capture(commands, returncode, "\n".join(output), cap)

    def run_selected(self, env, repo, files, names, timeout, cap, jobs):
        del names, jobs
        outcomes, timed_out, commands, returncode, output = self._run(files or [], env, repo, timeout, self.node_name)
        return outcomes, timed_out, self._capture(commands, returncode, output, cap)

    @staticmethod
    def _capture(commands, returncode, output, cap):
        clipped, truncated = cap.clip(output)
        return {
            "command": "\n".join(commands),
            "returncode": returncode,
            "text": clipped,
            "truncated": truncated,
        }
