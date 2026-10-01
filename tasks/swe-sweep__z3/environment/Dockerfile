# Maximally-buggy z3 — one recipe for every 4.x candidate anchor.
#
# Built upstream by `pandora construct build-image -t z3@<v>`, which prepares the build context
# under data/tasks/z3/maxbug/<v>/context/: it exports the z3 source tree at the candidate
# tag FROM THE LOCAL CLONE (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md) into ./z3, and copies this file in as
# ./Dockerfile.
#
# Why trixie and not bookworm: z3 does not just ask CMake for C++20, it uses it —
# `src/ast/ast.cpp` and friends `#include <format>`, which bookworm's gcc-12 does not
# ship, so the whole `ast` component fails to compile there. trixie's gcc-14 has it, and
# it is period-correct for the 4.15/4.16 anchors. Everything else z3 needs is small: it
# vendors its own bignum arithmetic, so the only real build dependency is a Python 3
# interpreter, which the build uses to generate the API and the parameter tables
# (`find_package(Python3 REQUIRED COMPONENTS Interpreter)`).
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
 && git clone --quiet --no-checkout https://github.com/Z3Prover/z3.git /src \
 && git -C /src checkout --quiet z3-4.16.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM debian:trixie-slim
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        git cmake ninja-build gcc g++ make pkg-config ca-certificates \
        python3 python-is-python3; \
    rm -rf /var/lib/apt/lists/*

# z3 source tree at the candidate ref, exported from the local clone into the build
# context (see the header).
COPY --from=swesweep-src /src /z3
WORKDIR /z3

# Make the exported tree a git repo (the export carries no .git), commit the source and
# tag it `baseline` — a SOURCE-ONLY tree, so an agent's extracted patch can never carry a
# build artifact. The build directory is /build, OUTSIDE the repo, so the consumers'
# `git reset --hard baseline && git clean -fdq` cannot touch it.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "z3 maxbug source" && git tag baseline

# Z3_INCLUDE_GIT_HASH/DESCRIBE are on by default and read `git describe`, which has
# nothing to describe in a tree whose only tag is `baseline`; both are turned off rather
# than papered over with a fake version tag.
#
# `test-z3` is EXCLUDE_FROM_ALL (src/test/CMakeLists.txt), so it has to be named as its
# own target. Building it here — not just libz3 — is what makes a subtask's rebuild
# incremental: the changed component recompiles and the driver relinks, instead of the
# whole solver being compiled from scratch.
RUN cmake -S /z3 -B /build -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DZ3_INCLUDE_GIT_HASH=OFF \
        -DZ3_INCLUDE_GIT_DESCRIBE=OFF \
        -DZ3_BUILD_LIBZ3_SHARED=ON \
    && cmake --build /build -j "$(nproc)" \
    && cmake --build /build -j "$(nproc)" --target test-z3

CMD ["/build/test-z3", "-h"]
