# Maximally-buggy sqlglot — frozen at anchor version 26.1.0.
#
# Built upstream by `pandora construct build-image -t sqlglot@26.1.0`, which prepares the build
# context from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the sqlglot source tree at
# v26.1.0 into ./sqlglot and copies this file in as ./Dockerfile. The image holds the
# sqlglot git tree with a `baseline` commit+tag; the host-controlled evaluator
# (tasks/sqlglot/task.yaml) does `git reset --hard baseline`, then applies the
# per-bug test/gold patches.
#
# sqlglot is PURE PYTHON here, and deliberately so. The repo also ships `sqlglotrs`, a Rust
# reimplementation of the tokenizer that sqlglot uses *if the wheel is importable* and
# ignores otherwise. Installing it would mean a Rust toolchain in the image, a maturin build
# on every gold patch that touches it, and a graded tokenizer that differs from the one the
# repo's own `python -m pytest` exercises by default. So it is left out: `baseline` is the
# whole truth, there is no build step, and the runner passes needs_build=False.
#
# Why 26.1.0 and not the coverage peak: sqlglot's curve peaks at 304 live subtasks in April
# 2024 and is still at 272 here (Jan 2025), but the *apply* rate moves the other way and
# faster. 88 subtasks have both patches applying at v23.9.0 (the peak) against 107 here —
# sqlglot's test fixtures are append-only text corpora that churn on nearly every commit, so
# a 2025 patch has no context to attach to in a 2024 tree. Measured in
# docs/ai/040-experiments/sqlglot/260820-anchor-choice.md.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/tobymao/sqlglot.git /src \
 && git -C /src checkout --quiet v26.1.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM python:3.12-slim-bookworm
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# git is needed in-container to reset/apply/clean between instances. sqlglot links against
# no system library, so that is the whole list.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends git ca-certificates; \
    rm -rf /var/lib/apt/lists/*

# The `dev` extra at this tag, minus what the test suite never imports. The linters (ruff,
# mypy, pre-commit) and the doc builder (pdoc) are contribution tooling, and `maturin` only
# exists to build sqlglotrs, which this image does not install. What is left is what
# tests/ actually reaches for: duckdb (the executor tests run real SQL through it), pandas
# (the dataframe and executor tests build frames), python-dateutil and pytz (the temporal
# annotation tests), and typing_extensions.
#
# Pinned to the releases current at the anchor date so the image stays period-correct: a
# duckdb or pandas from two years later changes what the executor tests observe.
RUN pip install --no-cache-dir \
        "pytest==8.3.4" \
        "duckdb==1.1.3" \
        "pandas==2.2.3" \
        "python-dateutil==2.9.0.post0" \
        "pytz==2024.2" \
        "typing_extensions==4.12.2" \
        "setuptools" \
        "setuptools_scm"

# sqlglot source tree at the anchor ref, exported from the local clone into the build
# context (see the header). It is imported straight from the working tree: the runner
# invokes pytest with cwd=/sqlglot, which puts /sqlglot on sys.path, so there is nothing to
# install and no build artifacts to keep in sync.
COPY --from=swesweep-src /src /sqlglot
WORKDIR /sqlglot

# setuptools_scm derives the version from git metadata, which the `git archive` export does
# not carry; without this, `import sqlglot` fails on the missing _version.py rather than on
# anything to do with the bug.
RUN printf '__version__ = "26.1.0"\n__version_tuple__ = (26, 1, 0)\n' > sqlglot/_version.py

# Make the exported tree a git repo (the export carries no .git), commit the source and tag
# it `baseline`. With no compiled core there is no artifact/source split to manage — the
# tree is source all the way down, so an agent's extracted patch is clean by construction.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "sqlglot maxbug source" && git tag baseline

# Prove the tree imports and its suite runs green before any patch is applied: a pristine
# failure reads as fails_pre_gold and quietly inflates the census with subtasks that
# reproduce nothing.
RUN python -m pytest tests/test_tokens.py -q -p no:cacheprovider -o addopts=

CMD ["python", "-c", "import sqlglot; print('sqlglot', sqlglot.__version__)"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
