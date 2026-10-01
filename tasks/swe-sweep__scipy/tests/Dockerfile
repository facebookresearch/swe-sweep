# Maximally-buggy scipy — frozen at anchor version v1.3.0.
#
# Built upstream by `pandora construct build-image -t scipy@1.3.0`, which prepares the build
# context under data/scipy/maxbug/1.3.0/context/: it exports the scipy source tree at
# v1.3.0 FROM THE LOCAL CLONE (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md) into ./scipy, and copies this file in as
# ./Dockerfile. The image holds the scipy git tree with a source-only `baseline`
# commit+tag; the host-controlled evaluator
# (tasks/scipy/task.yaml) does `git reset --hard
# baseline`, reuses the prebuilt (gitignored) extensions, then applies the per-bug
# test/gold patches.
#
# Why 1.3.0: the coverage curve over scipy's skim-accepted population peaks in spring
# 2019, and v1.3.0 (May 2019) sits on that plateau while also being the tag where the
# most upstream patches apply unrebased (see docs/ai/040-experiments/scipy/). scipy 1.3
# is Python-3-only (python_requires >= 3.5) and still builds through numpy.distutils
# (`setup.py build_ext`); the meson switch is 1.9. We base on python:3.7 (3.7 was
# current when v1.3.0 shipped, and is the newest interpreter this release claims).
# Debian buster is EOL and its apt repos moved to archive.debian.org, so we rewrite the
# sources first — the same dance as the numpy images.
#
# Built at Meta through FwdProxy exactly like the numpy images: `pandora construct
# build-image local` wraps the build in `sudo with-proxy` and passes `--network=host`,
# so the FROM pull + the apt/pip fetches below reach the network through the proxy
# (sudo because rootless podman can't route to FwdProxy's IPv6; see
# docs/ai/030-debug/260626-maxbug-image-registry-blocked.md). With FwdProxy in front of
# apt, apt's unprivileged `_apt` sandbox user can't read the proxied download, so we let
# apt run as root before touching the network.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/scipy/scipy.git /src \
 && git -C /src checkout --quiet v1.3.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM python:3.7-slim-buster
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# Point apt at the Debian archive (buster is EOL) and install the toolchain. git is
# needed in-container (reset/apply/clean between instances); gfortran + BLAS/LAPACK are
# hard requirements for scipy's Fortran core; the rest is its C/C++ build machinery.
RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    printf 'deb http://archive.debian.org/debian buster main\n\
deb http://archive.debian.org/debian-security buster/updates main\n' \
        > /etc/apt/sources.list; \
    apt-get -o Acquire::Check-Valid-Until=false update; \
    apt-get install -y --no-install-recommends \
        git gcc g++ gfortran make \
        libopenblas-dev liblapack-dev \
        ca-certificates; \
    rm -rf /var/lib/apt/lists/*

# Pin the build/test tooling to the v1.3.0 era (mid-2019). scipy 1.3's pyproject.toml
# asks for setuptools, wheel, Cython>=0.29.2 and numpy==1.14.5 on py3.7; we install
# numpy 1.16.4 instead — the release contemporary with v1.3.0, which satisfies the
# runtime floor (>=1.13.3) and has cp37 wheels. pytest 4.x is the suite's own era;
# pytest 5+ drops the `pytest.config` style scipy still uses in places.
# --no-build-isolation is implied: we never invoke a PEP 517 frontend, only setup.py.
RUN pip install --no-cache-dir \
        "setuptools<45" \
        "wheel<0.34" \
        "cython==0.29.10" \
        "numpy==1.16.4" \
        "pytest==4.6.11"

# scipy source tree at the anchor ref, exported from the local clone into the build
# context (see the header). NPY_NUM_BUILD_JOBS parallelizes the compile — scipy builds
# through numpy.distutils, which reads exactly that variable.
ENV NPY_NUM_BUILD_JOBS=4
COPY --from=swesweep-src /src /scipy
WORKDIR /scipy

# Make the exported tree a git repo (the export carries no .git), commit the source and
# tag it `baseline` — a SOURCE-ONLY tree. Build artifacts (.so/.pyc/generated .c/…) are
# NOT committed, so scipy's .gitignore keeps them out of `git diff` and a plain
# `git add -A` never stages them — this is what keeps an agent's extracted patch free of
# binary blobs. The build_ext below leaves those artifacts in the tree; being gitignored
# they SURVIVE the consumers' `git reset --hard baseline && git clean -fdq` (no -x), so
# scipy stays importable with no rebuild. Only a source-changing patch (agent/gold)
# triggers a rebuild afterwards.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "scipy maxbug source" && git tag baseline
RUN python setup.py build_ext --inplace

CMD ["python", "-c", "import scipy; print('scipy', scipy.__version__)"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
