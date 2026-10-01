# Maximally-buggy shapely — the 2.0 anchor candidate (2.0.0).
#
# Same shape as Dockerfile-1.8 (read that header for what the build context is, and why
# the tree is committed to `baseline` *before* the build). Two things differ, and both
# come from 2.0 being a different implementation rather than a later release of the same
# one:
#
# - The core is a **C extension** (`src/ufuncs.c`, `src/pygeom.c`, `src/coords.c`) that
#   calls the GEOS C API directly, not a ctypes shim. Its build is the real one, and a
#   gold patch that touches `src/` needs it re-run.
# - The version comes from **versioneer**, i.e. from `git describe`. The exported tree
#   carries no tags of its own, so the anchor version is tagged alongside `baseline`;
#   without it `shapely.__version__` reports `0+untagged`.
#
# GEOS is Debian bookworm's 3.11.1, the release contemporary with shapely 2.0.0.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/shapely/shapely.git /src \
 && git -C /src checkout --quiet 2.0.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM python:3.11-slim-bookworm
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        git ca-certificates build-essential libgeos-dev; \
    rm -rf /var/lib/apt/lists/*

# Pinned to the 2.0.0 era (Dec 2022).
RUN pip install --no-cache-dir \
        "setuptools==65.6.3" \
        "wheel==0.38.4" \
        "cython==0.29.33" \
        "numpy==1.24.1" \
        "pytest==7.2.1"

COPY --from=swesweep-src /src /shapely
WORKDIR /shapely

RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "shapely maxbug source" \
    && git tag baseline && git tag 2.0.0
RUN python setup.py build_ext --inplace

CMD ["python", "-c", "import shapely; print('shapely', shapely.__version__, 'geos', shapely.geos_version)"]
