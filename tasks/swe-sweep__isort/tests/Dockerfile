# Maximally-buggy isort — frozen at anchor version 5.10.1.
#
# Built upstream by `pandora construct build-image -t isort@5.10.1`, which prepares the build context
# from the local clone (no GitHub access — see docs/ai/010-design/005-style-conventions.md):
# it exports the source tree at 5.10.1 into ./isort and copies this file in as ./Dockerfile.
# The image holds the tree with a `baseline` commit+tag; the host-controlled evaluator
# (tasks/isort/task.yaml) does `git reset --hard baseline`, then applies the per-bug
# test/gold patches.
#
# isort is PURE PYTHON: no build step, `baseline` is the whole truth, and the runner passes
# needs_build=False.
#
# Why 5.10.1 and not the top of the curve: 5.3.2 has more live subtasks (30 against ~20) but
# almost none of its *test* patches apply there — 4, against 21 at 5.10.1 — because isort
# reorganised `tests/` into `unit/` and `integration/` right after 5.3, so every later test
# patch addresses a path the 5.3 tree does not have. See
# docs/ai/040-experiments/isort/260820-anchor-choice.md.
#
# Why Python 3.9: 5.10.1 is November 2021 and declares `python >=3.6.1,<4.0`.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/pycqa/isort.git /src \
 && git -C /src checkout --quiet 5.10.1 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM python:3.9-slim-bullseye
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends git ca-certificates; \
    rm -rf /var/lib/apt/lists/*

# The dev dependencies the unit suite actually imports. `hypothesis` and `hypothesmith`
# drive the property-based tests, `pytest-mock` the CLI ones, and `colorama` is the `colors`
# extra a handful of output tests assert against. The rest of poetry's dev group is
# linting, docs and packaging — none of it runs here.
RUN pip install --no-cache-dir \
        "pytest==6.2.5" \
        "pytest-mock==1.13.0" \
        "hypothesis==6.24.6" \
        "hypothesmith==0.2.0" \
        "colorama==0.4.4" \
        "setuptools"

# isort is a flat-layout package imported straight from the working tree: the runner invokes
# pytest with cwd=/isort, which puts /isort on sys.path, so there is nothing to install.
COPY --from=swesweep-src /src /isort
WORKDIR /isort

RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "isort maxbug source" && git tag baseline

# Prove the suite is green before any patch is applied.
RUN python -m pytest tests/unit/test_regressions.py -q -p no:cacheprovider -o addopts=

CMD ["python", "-c", "import isort; print('isort', isort.__version__)"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
