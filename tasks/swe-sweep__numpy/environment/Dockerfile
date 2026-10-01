# Maximally-buggy numpy — frozen at maxbug version v1.15.0.
#
# Built upstream by `pandora tasks build-image -t numpy --version 1.15.0`, which prepares the
# build context under data/numpy/maxbug/1.15.0/context/: it exports the numpy source
# tree at v1.15.0 FROM THE LOCAL CLONE (no GitHub access — see the 1.11.2 Dockerfile
# and docs/ai/intent/005-conventions.md) into ./numpy, and copies this file in as
# ./Dockerfile. The image holds the numpy git tree with a source-only `baseline`
# commit+tag; the host-controlled evaluator
# (tasks/numpy/task.yaml) does `git reset --hard baseline`,
# reuses the prebuilt (gitignored) extensions, then applies the per-bug test/gold patches.
#
# Why 1.15.0: it is the release where numpy's own test suite moved from nose to pytest
# (mid-2018), the hypothesised cliff above which far more upstream test patches graft
# onto the frozen tree (see docs/ai/experiments/numpy/). numpy 1.15 supports CPython
# 3.4–3.7; we base on python:3.7 (3.7.0 shipped June 2018, contemporary with the
# v1.15.0 tag). Debian stretch is EOL and its apt repos moved to archive.debian.org, so
# we rewrite the sources first. We build the C extensions in place from the actual
# frozen source (not a modern wheel).
#
# Built at Meta through FwdProxy exactly like the 1.11.2 image: `pandora tasks
# build-image` wraps the build in `sudo with-proxy` and passes `--network=host`, so the
# FROM pull + the apt/pip fetches below reach the network through the proxy (sudo
# because rootless podman can't route to FwdProxy's IPv6; see
# docs/ai/debug/260626-maxbug-image-registry-blocked.md). With FwdProxy in front of apt,
# apt's unprivileged `_apt` sandbox user can't read the proxied download, so we let apt
# run as root before touching the network.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/numpy/numpy.git /src \
 && git -C /src checkout --quiet v1.15.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM python:3.7-slim-stretch
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# Point apt at the Debian archive (stretch is EOL) and install the toolchain. git is
# needed in-container (reset/apply/clean between instances); gfortran + BLAS/LAPACK
# give numpy a real linalg backend; the rest is numpy's C/build machinery.
RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    printf 'deb http://archive.debian.org/debian stretch main\n\
deb http://archive.debian.org/debian-security stretch/updates main\n' \
        > /etc/apt/sources.list; \
    apt-get -o Acquire::Check-Valid-Until=false update; \
    apt-get install -y --no-install-recommends \
        git gcc g++ gfortran make \
        libopenblas-dev liblapack-dev \
        ca-certificates; \
    rm -rf /var/lib/apt/lists/*

# Pin the build/test tooling to the v1.15.0 era (mid-2018). numpy 1.15 builds its C
# extensions from the git tree with Cython >= 0.28; its suite runs on pytest (the
# nose→pytest migration release), which the host-controlled evaluator drives. nose is kept
# because numpy.testing still re-exports nose-based decorators at 1.15.
# --no-build-isolation keeps the pinned setuptools in control of the build below.
RUN pip install --no-cache-dir \
        "setuptools<41" \
        "wheel<0.34" \
        "cython==0.28.5" \
        "nose==1.3.7" \
        "pytest==3.8.2"

# numpy source tree at the maxbug ref, exported from the local clone into the build
# context (see the header). NPY_NUM_BUILD_JOBS parallelizes the C compile.
ENV NPY_NUM_BUILD_JOBS=4
COPY --from=swesweep-src /src /numpy
WORKDIR /numpy

# Make the exported tree a git repo (the export carries no .git), commit the source and
# tag it `baseline` — a SOURCE-ONLY tree. Build artifacts (.so/.pyc/…) are NOT committed,
# so numpy's .gitignore keeps them out of `git diff` and a plain `git add -A` never stages
# them — this is what keeps an agent's extracted patch free of binary blobs. The build_ext
# below leaves those artifacts in the tree; being gitignored they SURVIVE the consumers'
# `git reset --hard baseline && git clean -fdq` (no -x), so numpy stays importable with no
# rebuild. Only a source-changing patch (agent/gold) triggers a rebuild afterwards.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "numpy maxbug source" && git tag baseline
RUN python setup.py build_ext --inplace -j 4

CMD ["python", "-c", "import numpy as np; print('numpy', np.__version__)"]
