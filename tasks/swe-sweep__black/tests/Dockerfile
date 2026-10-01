# Maximally-buggy black — frozen at anchor version 23.3.0.
#
# Built upstream by `pandora construct build-image -t black@23.3.0`, which prepares the build
# context from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the black source tree at 23.3.0
# into ./black and copies this file in as ./Dockerfile. The image holds the black git tree
# with a `baseline` commit+tag; the host-controlled evaluator
# (tasks/black/task.yaml) does `git reset --hard baseline`, then applies the
# per-bug test/gold patches.
#
# black is PURE PYTHON: there is no compile step (the mypyc wheel hook is off by default),
# so an editable install makes a gold patch live the moment it applies and the runner
# passes needs_build=False.
#
# **The version file is the thing to get right.** `src/black/__init__.py` starts with
# `from _black_version import version`, and `src/_black_version.py` is not in the tree — it
# is written at build time by hatch-vcs from the git tag. The export carries no .git, so
# the tag has to exist *before* the install, which is why this file tags the tree twice:
# `23.3.0` so hatch-vcs derives the shipped version, and `baseline` for the runner to reset
# to. The generated file is gitignored, so it stays out of the baseline commit and survives
# the runner's `git clean -fdq` (deliberately not `-fdx`).
#
# Python 3.11 is the period-correct interpreter: black 23.3.0 (March 2023) targets it, and
# `tests/data/py_311/` needs a 3.11 parser for those cases to run rather than skip.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/psf/black.git /src \
 && git -C /src checkout --quiet 23.3.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM python:3.11-slim-bookworm
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# git supports the host-directed reset/apply between instances. black links against no
# system library, so that is the whole list.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends git ca-certificates; \
    rm -rf /var/lib/apt/lists/*

# Runtime, optional-extra and test dependencies at versions from this tag's era. The
# `jupyter` extra (ipython + tokenize-rt) and the `d` extra (aiohttp) are installed rather
# than skipped: without them `tests/test_ipynb.py` and `tests/test_blackd.py` skip whole
# files, and a large slice of the census would report "no targets" for bugs that reproduce
# perfectly well.
RUN pip install --no-cache-dir \
        "click==8.1.3" \
        "mypy-extensions==1.0.0" \
        "packaging==23.0" \
        "pathspec==0.11.1" \
        "platformdirs==3.2.0" \
        "colorama==0.4.6" \
        "aiohttp==3.8.4" \
        "ipython==8.12.0" \
        "tokenize-rt==5.0.0" \
        "pytest==7.2.2" \
        "pytest-xdist==3.0.2" \
        "hatchling==1.14.0" \
        "hatch-vcs==0.3.0" \
        "hatch-fancy-pypi-readme==22.8.0"

# black source tree at the anchor ref, exported from the local clone into the build context
# (see the header).
COPY --from=swesweep-src /src /black
WORKDIR /black

# Make the exported tree a git repo, commit the source, and tag it with the version so
# hatch-vcs can derive it. `baseline` is added after the install, on the same commit: it is
# what the runner resets to, and it is not a version-shaped tag, so it cannot confuse
# setuptools-scm on a later rebuild.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "black maxbug source" \
    && git tag 23.3.0

# Editable, no build isolation: the backend is already installed above, and an editable
# install is what keeps a patched `src/black/*.py` live without a rebuild. This also runs
# the hatch-vcs hook that writes `src/_black_version.py`.
RUN pip install --no-cache-dir --no-build-isolation -e .

RUN git tag baseline

# Prove the suite is green before any patch is applied: a pristine failure reads as
# fails_pre_gold and quietly inflates the census with subtasks that reproduce nothing. All
# three drivers the runner can select are checked — the fixture-corpus driver, the
# unit/CLI driver and the notebook driver.
RUN python -m pytest tests/test_format.py -q -p no:cacheprovider -o addopts= \
    && python -m pytest tests/test_black.py -q -p no:cacheprovider -o addopts= -x \
         -k "get_features_used or preserves_line_endings or format_file_contents" \
    && python -m pytest tests/test_ipynb.py -q -p no:cacheprovider -o addopts= -x \
         -k "non_python_magics or entire_notebook_empty_metadata"

CMD ["python", "-c", "import black; print('black', black.__version__)"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
