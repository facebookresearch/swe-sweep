# Maximally-buggy sunpy — frozen at anchor version v3.0.0.
#
# Built upstream by `pandora construct build-image -t sunpy@3.0.0`, which prepares the build
# context under data/sunpy/maxbug/3.0.0/context/: it exports the sunpy source tree at
# v3.0.0 FROM THE LOCAL CLONE (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md) into ./sunpy, and copies this file in as
# ./Dockerfile. The image holds the sunpy git tree with a `baseline` commit+tag; the
# host-controlled evaluator (tasks/sunpy/task.yaml) does
# `git reset --hard baseline`, then applies the per-bug test/gold patches.
#
# sunpy is PURE PYTHON: no compiled core, so this image has no build step, `baseline` is
# the whole truth, and neither the reproduce nor the eval runner rebuilds anything after a
# patch (both pass needs_build=False).
#
# Why 3.0.0: the later anchor candidate (May 2021), mid-run in sunpy's densest
# crawled-bug years (2019-2022).
#
# NOTE the base is the FULL python image, not `-slim`. The runners need `git` inside the
# container, and on this infra apt cannot get it: `deb.debian.org` is unreachable through
# FwdProxy and the archive.debian.org rewrite the older images use only carries EOL
# suites. The non-slim images are built on buildpack-deps and already ship git, so the
# apt step goes away entirely.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/sunpy/sunpy.git /src \
 && git -C /src checkout --quiet v3.0.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM python:3.9-bullseye
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# Runtime + test dependencies, pinned to the v3.0.0 era, taken from the release's own
# setup.cfg (install_requires plus the `tests` extra).
# sunpy's `tests` extra is not optional: sunpy/conftest.py and the suite import
# pytest-astropy, pytest-doctestplus, pytest-mock and hypothesis, and a missing one
# is a conftest ImportError that fails collection for the whole suite.
# numpy goes in FIRST and astropy is then built against it with --no-build-isolation.
# Without that, PEP 517 build isolation compiles astropy's C extensions against whatever
# numpy is newest at build time, and the pinned older runtime numpy then fails the C-ABI
# check ("module compiled against API version 0x10 but this version of numpy is 0xd") --
# which surfaces as a collection error on every sunpy test that touches astropy.wcs.
# pytest-cov is pinned for a second, unrelated resolution hazard: pytest-astropy pulls it
# in unpinned, pip takes the newest, and a modern pytest-cov calls
# pytest.hookimpl(wrapper=True) -- pytest 8 API -- which blows up at plugin import under
# the era-correct pytest 6, again as a collection error across the whole suite.
# pyparsing is pinned for a third: sunpy sets filterwarnings=error, and matplotlib 3.4
# trips a PyparsingDeprecationWarning against modern pyparsing at import -- which under
# that setting is a hard error, so again nothing collects.
RUN pip install --no-cache-dir \
        "numpy==1.20.3" \
        "setuptools<60" \
        "wheel<0.38" \
        "Cython<3" \
        "extension-helpers<1" \
        "setuptools_scm<7"
RUN pip install --no-cache-dir --no-build-isolation \
        "astropy==4.2.1" \
        "parfive==1.2.0" \
        "scipy==1.6.3" \
        "matplotlib==3.4.2" \
        "pyparsing==2.4.7" \
        "pandas==1.2.4" \
        "pytest==6.2.4" \
        "pytest-astropy==0.8.0" \
        "pytest-cov==2.12.1" \
        "pytest-doctestplus==0.9.0" \
        "pytest-mock==3.6.1" \
        "hypothesis==6.13.1"

# sunpy source tree at the anchor ref, exported from the local clone into the build
# context (see the header). It is imported straight from the working tree: the runners
# invoke pytest with cwd=/sunpy, which puts /sunpy on sys.path, so there is nothing to
# install and no build artifacts to keep in sync.
COPY --from=swesweep-src /src /sunpy
WORKDIR /sunpy

# Make the exported tree a git repo (the export carries no .git), commit the source and
# tag it `baseline`. With no compiled core there is no artifact/source split to manage —
# the tree is source all the way down, so an agent's extracted patch is clean by
# construction.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "sunpy maxbug source" && git tag baseline

CMD ["python", "-c", "import sunpy; print('sunpy', sunpy.__version__)"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
