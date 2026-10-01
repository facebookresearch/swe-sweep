# Maximally-buggy mpmath — frozen at anchor version 1.1.0.
#
# Built upstream by `pandora construct build-image -t mpmath@1.1.0`, which prepares the build
# context under data/mpmath/maxbug/1.1.0/context/: it exports the mpmath source tree at
# tag 1.1.0 FROM THE LOCAL CLONE (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md) into ./mpmath, and copies this file in as
# ./Dockerfile. The image holds the mpmath git tree with a `baseline` commit+tag; the
# host-controlled evaluator (tasks/mpmath/task.yaml) does
# `git reset --hard baseline`, then applies the per-bug test/gold patches.
#
# Like sympy, mpmath is PURE PYTHON: there is no compiled core, so the image has no
# build step and neither the reproduce nor the eval runner rebuilds anything after a
# patch (needs_build: false).
#
# Why 1.1.0 (Dec 2018): the SZZ coverage curve peaks at 44 live subtasks in Feb 2019,
# and 1.1.0 is the released tag closest to that peak (43 live).
#
# mpmath can use gmpy2 as a faster integer backend. It is deliberately NOT installed:
# the pure-Python backend is what every crawled fix was written against, and the two
# backends round differently in a handful of places, which is exactly the kind of
# difference that would show up as a spurious pre-gold failure.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/mpmath/mpmath.git /src \
 && git -C /src checkout --quiet 1.1.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM python:3.7-slim-buster
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# Point apt at the Debian archive (buster is EOL) and install git — needed in-container
# to reset/apply/clean between instances. That is the entire system dependency list.
# With FwdProxy in front of apt, apt's unprivileged `_apt` sandbox user can't read the
# proxied download, so let apt run as root first.
RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    printf 'deb http://archive.debian.org/debian buster main\n\
deb http://archive.debian.org/debian-security buster/updates main\n' \
        > /etc/apt/sources.list; \
    apt-get -o Acquire::Check-Valid-Until=false update; \
    apt-get install -y --no-install-recommends git ca-certificates; \
    rm -rf /var/lib/apt/lists/*

# mpmath 1.1.0 has no runtime dependencies at all. pytest 4.6.x is the suite's own era.
RUN pip install --no-cache-dir "pytest==4.6.11"

# mpmath source tree at the anchor ref, exported from the local clone into the build
# context (see the header). It is imported straight from the working tree: the runners
# invoke pytest with cwd=/mpmath, which puts /mpmath on sys.path, so there is nothing to
# install and no build artifacts to keep in sync.
COPY --from=swesweep-src /src /mpmath
WORKDIR /mpmath

# Make the exported tree a git repo (the export carries no .git), commit the source and
# tag it `baseline`.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "mpmath maxbug source" && git tag baseline

CMD ["python", "-c", "import mpmath; print('mpmath', mpmath.__version__)"]
