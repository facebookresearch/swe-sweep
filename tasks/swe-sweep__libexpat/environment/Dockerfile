# Maximally-buggy libexpat — frozen at candidate anchor version R_2_4_3.
#
# Built upstream by `pandora construct build-image -t libexpat@2.4.3`, which prepares the build
# context under data/libexpat/maxbug/2.4.3/context/: it exports the libexpat source tree
# at R_2_4_3 FROM THE LOCAL CLONE (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md) into ./libexpat, and copies this file in
# as ./Dockerfile.
#
# Why R_2_4_3: libexpat's bug-coverage curve peaks at 27 live subtasks in 2019-08, but
# the curve is a long plateau rather than a spike and the *tags* on it are all in the
# low twenties. R_2_4_3 (2022-01) carries 26 — one below the all-time peak, three years
# newer, and the highest of any release tag.
#
# Why bookworm: expat 2.4 needs a C compiler, a C++ compiler and cmake, and nothing else.
# It vendors no dependencies and links only libm.
#
# Built at Meta through FwdProxy like every other maxbug image, so apt is told to run as
# root before it touches the network (its unprivileged `_apt` sandbox user cannot read a
# proxied download).
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/libexpat/libexpat.git /src \
 && git -C /src checkout --quiet R_2_4_3 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

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
        git cmake ninja-build gcc g++ make bash ca-certificates \
        python3 python-is-python3; \
    rm -rf /var/lib/apt/lists/*
# bash is load-bearing, not a convenience: `expat_add_test` registers every test as
# `bash run.sh <binary>` (a generated wrapper that points the loader at the freshly built
# shared library), so a shell-less image registers tests that cannot start.
# The Python alias is retained only for repository-owned tooling.

# libexpat source tree at the candidate ref, exported from the local clone into the build
# context (see the header).
COPY --from=swesweep-src /src /libexpat
WORKDIR /libexpat

# Make the exported tree a git repo (the export carries no .git), commit the source and
# tag it `baseline` — a SOURCE-ONLY tree, so an agent's extracted patch can never carry a
# build artifact. Nothing is built inside the tree: the build directory is /build,
# OUTSIDE the repo, so the consumers' `git reset --hard baseline && git clean -fdq`
# cannot touch it.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "libexpat maxbug source" && git tag baseline

# The cmake project is one directory down (`expat/`); the repository root holds only the
# project scaffolding. EXPAT_BUILD_FUZZERS stays off: the fuzz targets refuse to build
# with anything but clang.
#
# Warming the build here is what makes a subtask's rebuild incremental — one recompile of
# `runtests.c` and a relink instead of a cold configure-and-build.
RUN cmake -S /libexpat/expat -B /build -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DEXPAT_BUILD_TESTS=ON \
        -DEXPAT_BUILD_FUZZERS=OFF \
        -DEXPAT_SHARED_LIBS=ON \
    && cmake --build /build -j 8

CMD ["ctest", "--test-dir", "/build", "-N"]
