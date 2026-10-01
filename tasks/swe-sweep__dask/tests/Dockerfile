# Maximally-buggy dask — frozen at anchor version 2.28.0.
#
# Built upstream by `pandora construct build-image -t dask@2.28.0`, which prepares the build context
# from the local clone (no GitHub access — see docs/ai/010-design/005-style-conventions.md):
# it exports the source tree at 2.28.0 into ./dask and copies this file in as ./Dockerfile.
# The image holds the tree with a `baseline` commit+tag; the host-controlled evaluator
# (tasks/dask/task.yaml) does `git reset --hard baseline`, then applies the per-bug
# test/gold patches.
#
# dask is PURE PYTHON: no build step, `baseline` is the whole truth, and the runner passes
# needs_build=False.
#
# Why 2.28.0: the top of the coverage curve (76 live subtasks) and tied for the best apply
# rate (31 gold+test pairs, the same as 2.9.1, which has one fewer live). It is by far the
# largest task in batch 15 — 486 skim-accepted subtasks against ~100 for the rest. See
# docs/ai/040-experiments/260820-batch15-go-python-anchors.md.
#
# Why Python 3.8: `continuous_integration/environment-3.8.yaml` is this tag's own CI
# environment, and the pins below are its required ones — python 3.8, numpy 1.17/1.19,
# pandas 1.0.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/dask/dask.git /src \
 && git -C /src checkout --quiet 2.28.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM python:3.8-slim-bullseye
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends git ca-certificates; \
    rm -rf /var/lib/apt/lists/*

# The dependencies of the four collection APIs the census can actually run — array,
# dataframe, bag and delayed — plus pytest. The rest of the CI environment is IO backends
# (pyarrow, s3fs, fastparquet, tiledb, hdf5) and `distributed`, which is a separate
# repository and needs a cluster; the tests that reach for those skip cleanly here rather
# than failing, which is why they are left out.
#
# psutil is the one dependency not pinned to the tag's era: it is a C extension, its 2020
# releases ship no cp38 wheel any more, and building one would mean carrying a compiler in
# the image. dask only uses it to count cores, so the version does not affect any verdict.
RUN pip install --no-cache-dir \
        "numpy==1.19.5" \
        "pandas==1.0.5" \
        "toolz==0.11.1" \
        "cloudpickle==1.6.0" \
        "partd==1.1.0" \
        "fsspec==0.8.4" \
        "pyyaml==5.3.1" \
        "psutil==5.9.8" \
        "pytest==6.1.1" \
        "setuptools"

# dask is a flat-layout package imported straight from the working tree: the runner invokes
# pytest with cwd=/dask, which puts /dask on sys.path, so there is nothing to install.
COPY --from=swesweep-src /src /dask
WORKDIR /dask

RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "dask maxbug source" && git tag baseline

# Prove the suite is green before any patch is applied: a pristine failure reads as
# fails_pre_gold and quietly inflates the census with subtasks that reproduce nothing. Both
# halves are checked — the scheduler core, and a dataframe module, which is the part most
# sensitive to the pandas pin.
RUN python -m pytest dask/tests/test_core.py -q -p no:cacheprovider -o addopts= \
    && python -m pytest dask/dataframe/tests/test_arithmetics_reduction.py -q -p no:cacheprovider -o addopts= -x -k "reductions_frame"

CMD ["python", "-c", "import dask; print('dask', dask.__version__)"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
