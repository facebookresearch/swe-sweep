# Maximally-buggy click — frozen at anchor version 8.0.1.
#
# Built upstream by `pandora construct build-image -t click@8.0.1`, which prepares the build context
# from the local clone (no GitHub access — see docs/ai/010-design/005-style-conventions.md):
# it exports the source tree at 8.0.1 into ./click and copies this file in as ./Dockerfile.
# The image holds the tree with a `baseline` commit+tag; the host-controlled evaluator
# (tasks/click/task.yaml) does `git reset --hard baseline`, then applies the per-bug
# test/gold patches.
#
# click is PURE PYTHON: no build step, `baseline` is the whole truth, and the runner passes
# needs_build=False.
#
# Why 8.0.1: the top of the coverage curve (18 live subtasks) *and* the best host-side apply
# rate — 8 gold+test pairs apply here against 6 at both 8.1.0 and 8.1.3. See
# docs/ai/040-experiments/click/260820-anchor-choice.md.
#
# Why Python 3.9: 8.0.1 is May 2021 and declares `python_requires >= 3.6`; 3.9 is the
# period-correct interpreter. It also matters for behaviour, not just for installing —
# click's terminal and pathlib handling differs across versions, and a few tests assert on
# argparse-era error text.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/pallets/click.git /src \
 && git -C /src checkout --quiet 8.0.1 \
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

# git is needed in-container to reset/apply/clean between instances. click links against no
# system library, so that is the whole list.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends git ca-certificates; \
    rm -rf /var/lib/apt/lists/*

# The test dependency, at the version this tag's `requirements/tests.txt` pins. click itself
# has no runtime dependency on this interpreter (colorama is Windows-only).
RUN pip install --no-cache-dir "pytest==6.2.4"

# The source tree at the anchor ref, exported from the local clone into the build context
# (see the header). click uses a src layout, so it is installed rather than imported from
# the working tree — but as an *editable* install, so a gold patch is live the moment it
# applies, with nothing to rebuild.
COPY --from=swesweep-src /src /click
WORKDIR /click
RUN pip install --no-cache-dir -e .

RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "click maxbug source" && git tag baseline

# Prove the suite is green before any patch is applied: a pristine failure reads as
# fails_pre_gold and quietly inflates the census with subtasks that reproduce nothing.
RUN python -m pytest tests/test_basic.py -q -p no:cacheprovider -o addopts=

CMD ["python", "-c", "import click; print('click', click.__version__)"]
