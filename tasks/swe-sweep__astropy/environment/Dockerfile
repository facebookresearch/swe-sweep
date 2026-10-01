# Maximally-buggy astropy — frozen at anchor version v5.2.
#
# Built upstream by `pandora construct build-image -t astropy@5.2`, which prepares the build
# context under data/astropy/maxbug/5.2/context/: it exports the astropy source tree at
# v5.2 FROM THE LOCAL CLONE (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md) into ./astropy, and copies this file in as
# ./Dockerfile. The image holds the astropy git tree with a source-only `baseline`
# commit+tag; the host-controlled evaluator (tasks/astropy/task.yaml) does
# `git reset --hard baseline`, reuses the prebuilt (gitignored) extensions, then applies
# the per-bug test/gold patches.
#
# astropy has a COMPILED CORE (Cython + hand-written C wrapping the vendored libraries
# under cextern/), so the runners rebuild after a patch with the default
# `python setup.py build_ext --inplace`. The image runs that build once, so a subtask's
# rebuild only recompiles what its patch touched.
#
# Why 5.2, when the coverage curve peaks higher elsewhere: the curve's best tags are
# v3.2.3 (339 live) and the v4.0 series (~318), but **every astropy release up to and
# including 4.1 carries `astropy_helpers` as a git submodule**, and `git archive` exports
# a submodule as an empty directory — the export would not build at all without either
# vendoring the helpers or letting `ah_bootstrap` fetch them from PyPI at build time.
# v5.2 (Dec 2022) is the best tag with no submodule at all: 307 live, 36 short of the
# peak, on a modern setuptools/pyproject build.
#
# NOTE the base is the FULL python image, not `-slim`. The runners need `git` inside the
# container, and on this infra apt cannot get it: `deb.debian.org` is unreachable through
# FwdProxy. The non-slim images are built on buildpack-deps and already ship git and a C
# toolchain, so the apt step goes away entirely.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/astropy/astropy.git /src \
 && git -C /src checkout --quiet v5.2 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM python:3.10-bullseye
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# Build + runtime + test dependencies, pinned to the v5.2 era (Dec 2022).
# The build backend is pinned from this release's own pyproject.toml (cython==0.29.30,
# extension-helpers, setuptools_scm); numpy goes in first so the C extensions compile
# against the same numpy the runtime will import.
# The `test` extra is not optional: astropy's setup.cfg turns on `astropy_header`,
# `doctest_plus` and `--doctest-rst`, so a missing pytest-astropy-header or
# pytest-doctestplus is an ini-level error that kills collection for the whole suite
# rather than one test. pytest-astropy pulls the rest (remotedata, openfiles, arraydiff,
# filter-subpackage, hypothesis).
# scipy and matplotlib are the `recommended` extra: without them a large part of the
# suite skips rather than runs, which would quietly shrink the census.
# pyparsing is pinned for a separate reason: astropy's setup.cfg sets
# `filterwarnings = error`, and matplotlib 3.6 calls pyparsing APIs that a modern
# pyparsing warns about at import. Under that setting the warning is a hard error, so the
# whole suite fails to collect. 3.0.9 is the release contemporary with this astropy.
RUN pip install --no-cache-dir \
        "numpy==1.23.5" \
        "setuptools<66" \
        "wheel<0.39" \
        "cython==0.29.30" \
        "extension-helpers==1.0.0" \
        "setuptools_scm==7.0.5"
RUN pip install --no-cache-dir --no-build-isolation \
        "pyerfa==2.0.0.1" \
        "PyYAML==6.0" \
        "packaging==22.0" \
        "scipy==1.9.3" \
        "matplotlib==3.6.2" \
        "pyparsing==3.0.9" \
        "pytest==7.2.0" \
        "pytest-astropy==0.10.0" \
        "pytest-astropy-header==0.2.2" \
        "pytest-doctestplus==0.12.1" \
        "pytest-xdist==3.1.0"

# astropy source tree at the anchor ref, exported from the local clone into the build
# context (see the header). It is imported straight from the working tree: the runners
# invoke pytest with cwd=/astropy, which puts /astropy on sys.path, so there is nothing
# to install — only the in-place extensions to build.
COPY --from=swesweep-src /src /astropy
WORKDIR /astropy

# Make the exported tree a git repo (the export carries no .git), commit the source and
# tag it `baseline` — a SOURCE-ONLY tree, which is why this runs BEFORE the build. Build
# artifacts (.so, the Cython-generated .c, the setuptools_scm-generated
# astropy/_version.py) are all in astropy's own .gitignore, so a plain `git add -A` never
# stages them and an agent's extracted patch carries no binary blobs. Being gitignored
# they also SURVIVE the consumers' `git reset --hard baseline && git clean -fdq` (no -x),
# so astropy stays importable with no rebuild; only a source-changing patch triggers one.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "astropy maxbug source" && git tag baseline

# setuptools_scm derives the version from git tags, and the only tag in this repo is
# `baseline` — it would otherwise stamp a 0.1.dev version and astropy's own
# `__minimum_python_version__`/deprecation machinery reads it. Pretending the real
# version is both correct and stable across the rebuilds the runners do.
ENV SETUPTOOLS_SCM_PRETEND_VERSION=5.2

# --- the leap-second time bomb -------------------------------------------------------
#
# astropy ships a copy of the IERS leap-second table, and every release's copy expires
# about a year after it. Running a 2022 astropy in 2026, `astropy.time` notices the file
# is stale and emits an AstropyWarning; astropy's setup.cfg sets `filterwarnings = error`,
# so that warning is a hard failure in any test that touches a time scale — 1 of the 430
# in astropy/coordinates/tests/test_sky_coord.py, and a great deal more of
# astropy/time/ and astropy/coordinates/. It cannot be fixed by config: astropy's own
# conftest.py redirects XDG_CONFIG_HOME to a fresh temp dir so a user astropy.cfg is
# never read, and the container has no network to auto-update from.
#
# So it is turned off the one way that survives that conftest: a tiny pytest plugin,
# loaded through PYTEST_ADDOPTS (which the runners' `-o addopts=` does not clear), that
# sets the IERS config before any test runs. `auto_max_age = None` disables the staleness
# check; `auto_download = False` keeps the suite offline, which it has to be anyway.
RUN mkdir -p /opt/swesweep \
    && printf '%s\n' \
        'def pytest_configure(config):' \
        '    from astropy.utils.iers import conf' \
        '    conf.auto_download = False' \
        '    conf.auto_max_age = None' \
        > /opt/swesweep/swesweep_iers.py
ENV PYTHONPATH=/opt/swesweep
ENV PYTEST_ADDOPTS="-p swesweep_iers"

# Build the Cython/C extensions in place, once, so a subtask's rebuild is incremental.
RUN python setup.py build_ext --inplace -j "$(nproc)"

CMD ["python", "-c", "import astropy; print('astropy', astropy.__version__)"]
