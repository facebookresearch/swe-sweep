# Maximally-buggy pint — frozen at anchor version 0.18.
#
# Built upstream by `pandora construct build-image -t pint@0.18`, which prepares the build context
# from the local clone (no GitHub access — see docs/ai/010-design/005-style-conventions.md):
# it exports the source tree at 0.18 into ./pint and copies this file in as ./Dockerfile.
# The image holds the tree with a `baseline` commit+tag; the host-controlled evaluator
# (tasks/pint/task.yaml) does `git reset --hard baseline`, then applies the per-bug
# test/gold patches.
#
# pint is PURE PYTHON: no build step, `baseline` is the whole truth, and the runner passes
# needs_build=False.
#
# Why 0.18 and not the top of the curve: 0.16.1 has more live subtasks (26 against ~22) but
# only 3 gold+test pairs apply there, against 5 at 0.18 — pint reorganised its test suite in
# between, so the older tree cannot take the newer patches. See
# docs/ai/040-experiments/pint/260820-anchor-choice.md.
#
# Why Python 3.9: 0.18 is October 2021 and declares `python_requires >= 3.7`.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/hgrecco/pint.git /src \
 && git -C /src checkout --quiet 0.18 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

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

# The runtime and test dependencies this tag's setup.cfg names. numpy and uncertainties are
# optional extras, but they are what most of the suite exercises — without them the
# interesting half of the tests skip rather than run, which would silently shrink the census.
RUN pip install --no-cache-dir \
        "packaging==21.3" \
        "numpy==1.21.4" \
        "uncertainties==3.1.6" \
        "pytest==6.2.5" \
        "pytest-subtests==0.5.0" \
        "setuptools" "setuptools_scm"

COPY --from=swesweep-src /src /pint
WORKDIR /pint
# setuptools_scm derives the version from git metadata the export does not carry, so it is
# pinned explicitly for the install.
RUN SETUPTOOLS_SCM_PRETEND_VERSION=0.18 pip install --no-cache-dir -e . --no-build-isolation

RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "pint maxbug source" && git tag baseline

# Prove the suite is green before any patch is applied.
RUN python -m pytest pint/testsuite/test_util.py -q -p no:cacheprovider -o addopts=

CMD ["python", "-c", "import pint; print('pint', pint.__version__)"]
