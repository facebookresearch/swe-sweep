"""JestPerPackageSuite suite adapter."""

import os
import subprocess

from ..utils.logging import log
from .jest import JestSuite

class JestPerPackageSuite(JestSuite):
    """jest in a monorepo where **each package carries its own config** and the root
    aggregates nothing — aws-cdk's layout.

    :class:`JestSuite` runs one jest at the repo root, which works when the root config
    declares `projects` (react-router) or is the only config there is (webpack, jest). aws-cdk
    has neither: every package has a `jest.config.js` naming its own transform, and running
    jest from the root finds no config at all, so a TypeScript spec is handed to node
    untransformed and dies on `SyntaxError: Cannot use import statement outside a module`
    before a single test runs. That reads as a collection error in both states, which is a
    verdict about the harness rather than about the bug.

    So the spec files are grouped by the nearest ancestor holding a `jest.config.js`, and jest
    runs once per group from that directory with the paths rewritten relative to it. Outcomes
    from every group are merged, exactly as if one invocation had produced them.
    """

    no_targets = "test patch touched no JavaScript test files"

    def __init__(self, config_name="jest.config.js", compile_cmd=None, compiled_ext=None,
                 config_for=None, env=None, env_file=None):
        JestSuite.__init__(self)
        self.config_name = config_name
        self.compile_cmd = compile_cmd
        self.compiled_ext = compiled_ext
        # `config_for(package) -> path` names a config other than the package's default one,
        # for a repo that keeps several suites in one package (prisma's functional corpus has
        # its own jest config under tests/functional/).
        self.config_for = config_for
        self.env = dict(env or {})
        # A shell env file to source before running, for a repo whose own test script does the
        # same (prisma runs everything through `dotenv -e .db.env`, and its harness aborts on a
        # missing variable even for the providers it is not going to use).
        self.env_file = env_file

    def _package_of(self, env, repo, path):
        """The nearest ancestor of ``path`` holding the package's jest config, relative to
        ``repo``; ``""`` (the repo root) when there is none."""
        parts = path.split("/")[:-1]
        while parts:
            candidate = "/".join(parts)
            if env.exists(os.path.join(repo, candidate, self.config_name)):
                return candidate
            parts.pop()
        return ""

    def _as_compiled(self, path):
        """The spec path jest will actually match, when the suite runs compiled output."""
        if not self.compiled_ext:
            return path
        stem, ext = os.path.splitext(path)
        return stem + self.compiled_ext if ext in (".ts", ".tsx") else path

    def run_tests(self, environment, repo, files, names, timeout, jobs):
        groups = {}
        if files is None:
            for path in environment.find_files(repo):
                relative = os.path.relpath(path, repo)
                if any(part in (".git", "node_modules") for part in relative.split("/")[:-1]):
                    continue
                if os.path.basename(path) == self.config_name:
                    pkg = os.path.relpath(os.path.dirname(path), repo)
                    groups["" if pkg == "." else pkg] = []
        else:
            for f in files:
                pkg = self._package_of(environment, repo, f)
                groups.setdefault(pkg, []).append(f[len(pkg) + 1:] if pkg else f)
        outcomes = {}
        total = 0
        had_error = False
        for pkg, rel in sorted(groups.items()):
            cwd = os.path.join(repo, pkg)
            command_env = dict(self.env)
            if self.env_file:
                path = os.path.join(repo, self.env_file)
                if environment.exists(path):
                    for line in environment.read_text(path).splitlines():
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        command_env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            if self.compile_cmd:
                # The compile runs in BOTH states, which is the point: a test patch that adds
                # a `.ts` spec has added nothing jest can see until it is transpiled, so a
                # pre-gold run without this reports "no tests found" rather than a failure.
                log("$ (in %s) %s" % (pkg or ".", self.compile_cmd))
                try:
                    c = environment.execute(
                        self.compile_cmd,
                        shell=True,
                        cwd=cwd,
                        timeout=timeout,
                        env=command_env,
                        merge_stderr=True,
                    )
                except subprocess.TimeoutExpired:
                    log("compile TIMEOUT after %ds (%s)" % (timeout, pkg or "."))
                    return {}, 0, False, True
                log("compile rc=%d" % c.returncode)
                log(c.stdout[-1500:])
            extra = []
            if self.config_for:
                cfg = self.config_for(pkg)
                if cfg:
                    extra = ["--config", cfg]
            got, n, err, timed_out = JestSuite.run_tests(
                self, environment, cwd, [self._as_compiled(f) for f in rel], names, timeout, jobs,
                extra_args=extra, command_env=command_env)
            if timed_out:
                return {}, 0, False, True
            outcomes.update(got)
            total += n
            had_error = had_error or err
        return outcomes, total, had_error, False
