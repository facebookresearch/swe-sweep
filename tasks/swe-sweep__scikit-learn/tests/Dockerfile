# Maximally-buggy scikit-learn — frozen at anchor version 0.18.
#
# Built upstream by `pandora construct build-image -t scikit-learn@0.18`, which prepares the
# build context under data/scikit-learn/maxbug/0.18/context/: it exports the sklearn
# source tree at the 0.18 tag FROM THE LOCAL CLONE (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md) into ./scikit-learn, and copies this file
# in as ./Dockerfile. The image holds the sklearn git tree with a source-only `baseline`
# commit+tag; the host-controlled evaluator
# (tasks/scikit-learn/task.yaml) does `git reset --hard
# baseline`, reuses the prebuilt (gitignored) extensions, then applies the per-bug
# test/gold patches.
#
# Why 0.18: the coverage curve over scikit-learn's skim-accepted population peaks in
# late September 2016, essentially on this tag, and 0.18 is also where the most upstream
# patches apply unrebased (see docs/ai/040-experiments/scikit-learn/). 0.18 predates the
# nose→pytest migration (0.19), so nose is installed alongside pytest: sklearn's own
# `sklearn/utils/testing.py` imports nose at this release, while the test patches we
# graft on are pytest-shaped. It builds through numpy.distutils (`setup.py build_ext`);
# the meson switch is 1.5. python:3.5 is the newest interpreter this release claims.
# Debian stretch is EOL and its apt repos moved to archive.debian.org, so we rewrite the
# sources first — the same dance as the numpy images.
#
# Built at Meta through FwdProxy exactly like the numpy images: `pandora construct
# build-image local` wraps the build in `sudo with-proxy` and passes `--network=host`
# (sudo because rootless podman can't route to FwdProxy's IPv6; see
# docs/ai/030-debug/260626-maxbug-image-registry-blocked.md). With FwdProxy in front of
# apt, apt's unprivileged `_apt` sandbox user can't read the proxied download, so we let
# apt run as root before touching the network.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/scikit-learn/scikit-learn.git /src \
 && git -C /src checkout --quiet 0.18 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM python:3.5-slim-stretch
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# Point apt at the Debian archive (stretch is EOL) and install the toolchain. git is
# needed in-container (reset/apply/clean between instances); BLAS/LAPACK back the numpy
# and scipy that sklearn computes through; the rest is its C/C++ build machinery.
RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    printf 'deb http://archive.debian.org/debian stretch main\n\
deb http://archive.debian.org/debian-security stretch/updates main\n' \
        > /etc/apt/sources.list; \
    apt-get -o Acquire::Check-Valid-Until=false update; \
    apt-get install -y --no-install-recommends \
        git gcc g++ make \
        libopenblas-dev liblapack-dev \
        ca-certificates; \
    rm -rf /var/lib/apt/lists/*

# Pinned to the 0.18 era (Sept 2016). Unlike numpy/scipy, sklearn's own numeric stack is
# a DEPENDENCY, so it is pinned to the period releases (numpy 1.11.2 / scipy 0.18.1)
# rather than whatever is current — a modern numpy would not even import here. Cython
# 0.24.1 is the release contemporary with the tag; nose is what 0.18's test helpers
# import; pytest is what the validator drives the targeted tests with.
RUN pip install --no-cache-dir \
        "setuptools<45" \
        "wheel<0.34" \
        "cython==0.24.1" \
        "numpy==1.11.2" \
        "scipy==0.18.1" \
        "nose==1.3.7" \
        "pytest==4.6.11"

# sklearn source tree at the anchor ref, exported from the local clone into the build
# context (see the header). sklearn's build_ext is a numpy.distutils subclass, so the
# compile parallelism comes from NPY_NUM_BUILD_JOBS; SKLEARN_BUILD_PARALLEL is what
# later releases read and is set for symmetry with the 0.22 image.
ENV NPY_NUM_BUILD_JOBS=4 SKLEARN_BUILD_PARALLEL=4
COPY --from=swesweep-src /src /scikit-learn
WORKDIR /scikit-learn

# Make the exported tree a git repo (the export carries no .git), commit the source and
# tag it `baseline` — a SOURCE-ONLY tree. Build artifacts (.so/.pyc/generated .c/…) are
# NOT committed, so sklearn's .gitignore keeps them out of `git diff` and a plain
# `git add -A` never stages them — this is what keeps an agent's extracted patch free of
# binary blobs. The build_ext below leaves those artifacts in the tree; being gitignored
# they SURVIVE the consumers' `git reset --hard baseline && git clean -fdq` (no -x), so
# sklearn stays importable with no rebuild. Only a source-changing patch (agent/gold)
# triggers a rebuild afterwards.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "scikit-learn maxbug source" && git tag baseline
RUN python setup.py build_ext --inplace

CMD ["python", "-c", "import sklearn; print('scikit-learn', sklearn.__version__)"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
