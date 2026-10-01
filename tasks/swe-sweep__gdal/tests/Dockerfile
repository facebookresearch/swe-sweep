# Maximally-buggy GDAL — frozen at candidate anchor version v3.6.2.
#
# Built upstream by `pandora construct build-image -t gdal@3.6.2`, which prepares the build
# context under data/gdal/maxbug/3.6.2/context/: it exports the GDAL source tree at
# v3.6.2 FROM THE LOCAL CLONE (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md) into ./gdal, and copies this file in as
# ./Dockerfile.
#
# Why 3.6.2: GDAL's bug-coverage curve peaks in late January 2023 (401 live subtasks) and
# v3.6.2 is the release tag on that peak, with 393 — more than any other tag. It is also
# the release Debian bookworm packages, which is what the recipe below was validated
# against (docs/ai/040-experiments/gdal/260810-build-recipe-probe.md).
#
# Why bookworm: GDAL 3.6 needs PROJ >= 8, and bookworm ships PROJ 9.1, so the whole
# dependency set installs from the stock archive with no pinning or backports. GDAL
# vendors geotiff/gif/jsonc/opencad/qhull, so those need no system package.
#
# Built at Meta through FwdProxy like every other maxbug image: `pandora construct
# build-image` wraps the build in `sudo with-proxy` and passes `--network=host` (rootless
# podman can't route to FwdProxy's IPv6 — see
# docs/ai/030-debug/260626-maxbug-image-registry-blocked.md). With FwdProxy in front of
# apt, apt's unprivileged `_apt` sandbox user cannot read the proxied download, so apt is
# told to run as root before it touches the network.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/OSGeo/gdal.git /src \
 && git -C /src checkout --quiet v3.6.2 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM debian:bookworm-slim
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        git cmake ninja-build g++ pkg-config ca-certificates \
        libproj-dev libgeos-dev libsqlite3-dev sqlite3 libtiff-dev \
        libcurl4-openssl-dev libexpat1-dev libjpeg-dev libpng-dev \
        zlib1g-dev libwebp-dev libzstd-dev \
        python3-dev python3-numpy python3-pip python3-setuptools swig \
        python-is-python3; \
    rm -rf /var/lib/apt/lists/*
# GDAL's repository tests invoke `python -m pytest`, so Debian's `python3` needs the alias.

# The test tooling. GDAL's suite is pytest driving the library through its Python
# bindings, so this is all the runners need on top of the build.
RUN pip install --no-cache-dir --break-system-packages \
        "pytest==7.4.4" "pytest-sugar" "lxml"

# GDAL source tree at the candidate ref, exported from the local clone into the build
# context (see the header).
COPY --from=swesweep-src /src /gdal
WORKDIR /gdal

# Make the exported tree a git repo (the export carries no .git), commit the source and
# tag it `baseline` — a SOURCE-ONLY tree, so an agent's extracted patch can never carry a
# build artifact. Unlike the setup.py repos, nothing is built *inside* the tree at all:
# the build directory is /build, OUTSIDE the repo, so the consumers'
# `git reset --hard baseline && git clean -fdq` cannot touch it whether or not GDAL's
# .gitignore happens to cover it.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "gdal maxbug source" && git tag baseline

RUN cmake -S /gdal -B /build -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DBUILD_TESTING=ON \
        -DBUILD_PYTHON_BINDINGS=ON \
        -DBUILD_JAVA_BINDINGS=OFF \
        -DBUILD_CSHARP_BINDINGS=OFF \
    && cmake --build /build -j 8

# The suite imports `osgeo` from the build tree and loads libgdal from there too — no
# install step, so a rebuild after a gold/agent patch is picked up with no extra work.
ENV PYTHONPATH=/build/swig/python \
    LD_LIBRARY_PATH=/build \
    GDAL_DATA=/gdal/data

CMD ["python3", "-c", "from osgeo import gdal; print('gdal', gdal.__version__)"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
