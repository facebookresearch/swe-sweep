# Maximally-buggy Tarantool — frozen at the 2.10.0 tag (2022-05-22), the peak of the
# coverage curve and, by a wide margin, the candidate whose patches best survive to the
# anchor (see docs/ai/040-experiments/tarantool/).
#
# Built upstream by `pandora construct build-image -t tarantool@2.10.0`, which prepares the build
# context from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the source tree at that tag into
# ./tarantool, **including every submodule at its pinned commit**, and copies this file in
# as ./Dockerfile. The image holds the tree with a `baseline` commit+tag; the
# host-controlled evaluator (tasks/tarantool/task.yaml) does
# `git reset --hard baseline`, applies the per-bug test/gold patches, and rebuilds.
#
# Four things are specific to a Tarantool task:
#
# 1. **Almost everything it links is a submodule, and the harness is one too.** Tarantool
#    pins seventeen of them — LuaJIT, curl, zstd, libunwind, msgpuck, small, … — and
#    `test-run`, which runs the tests, is an eighteenth whose *own* submodules carry the
#    luatest runner and the Python client. The context export follows that nesting; nothing
#    is fetched here.
#
# 2. **The build is in-source, on purpose.** Tarantool's .gitignore covers the whole cmake
#    in-source footprint (`CMakeFiles`, `CMakeCache.txt`, the per-directory `Makefile`s,
#    `src/tarantool`, the generated LuaJIT headers), which is exactly what lets the
#    runner's `git reset --hard baseline` + `git clean -fdq` leave the object tree standing
#    between subtasks. The rebuild is therefore incremental — minutes for a leaf change
#    rather than the ~20 the first build costs.
#
# 3. **The graded product spans C and Lua.** A fix may land in the storage engine or in the
#    Lua module layer under `src/lua` and `src/box/lua`, and the Lua files are compiled
#    *into* the binary (`src/lua/*.lua.c` is generated), so even a one-line Lua fix needs
#    the rebuild. There is no interpret-in-place shortcut.
#
# 4. **The test harness compares output, it does not assert.** Most of `test/` is a
#    `.test.lua` script beside a checked-in `.result`, and test-run diffs them. `--retries 0`
#    matters for the census: test-run re-runs a failed test by default, which would turn a
#    deterministic pre-gold failure into a slow flake hunt.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/tarantool/tarantool.git /src \
 && git -C /src checkout --quiet 2.10.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM debian:bullseye
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# Exactly Tarantool's own `deps_debian_packages` list from .travis.mk, minus the Python 2
# half (dead) and the coverage/clang extras (unused here).
ENV DEBIAN_FRONTEND=noninteractive
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        build-essential cmake coreutils sed git curl ca-certificates \
        autoconf automake libtool pkg-config \
        libreadline-dev libncurses5-dev libyaml-dev libssl-dev \
        libcurl4-openssl-dev libunwind-dev libicu-dev zlib1g-dev \
        python3 python3-dev python3-pip python3-setuptools; \
    rm -rf /var/lib/apt/lists/*

# Tarantool source tree at the anchor tag, with every (nested) submodule exported into
# place — see the header.
COPY --from=swesweep-src /src /tarantool
WORKDIR /tarantool

# Make the exported tree a git repo (the export carries no .git), commit the source and tag
# it `baseline`. Before the build, so the whole in-source cmake footprint stays untracked
# and ignored, and therefore survives the runner's reset between subtasks.
#
# The second, *annotated* tag is what makes the build work at all: Tarantool takes its
# version from `git describe --long`, and the exported tree's fresh repository has no
# history to describe. It falls back to a `VERSION` file, which is gitignored and therefore
# not in the export either, and configure dies with "Unable to retrive version from git".
# An annotated tag naming the anchor gives `git describe` the answer upstream's own build
# would have got. `baseline` stays unannotated so it cannot be picked up instead.
# Bundled LuaJIT reads *its* version from git too, and there is only one repository here,
# so it asks the same `git describe` and is handed Tarantool's tag — which its own regex
# rejects, and it aborts configure. Its fallback is a hardcoded literal, so the fix is to
# take that branch with the value the submodule's real history would have produced. Written
# before the baseline commit so a subtask's reset cannot revert it; the file is build
# tooling under third_party/, which is neither graded source nor test, so no patch touches
# it.
RUN sed -i \
    -e 's|^  if(EXISTS ${CMAKE_SOURCE_DIR}/.git AND Git_FOUND)$|  if(FALSE)|' \
    -e 's|"v2\.1\.0-beta3-0-g0000000"|"v2.1.0-beta3-188-g359bfe09"|' \
    third_party/luajit/cmake/SetVersion.cmake \
    && grep -q 'v2.1.0-beta3-188-g359bfe09' third_party/luajit/cmake/SetVersion.cmake

RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "tarantool maxbug source" \
    && git tag baseline \
    && git tag -a -m "tarantool 2.10.0" 2.10.0

# test-run's runtime. Pinned by the harness itself (test-run/requirements.txt), not chosen
# here, so it stays period-correct with the submodule.
RUN pip3 install --no-cache-dir -r /tarantool/test-run/requirements.txt

# Several tests assert on non-ASCII strings round-tripping through the console.
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8

# One script for both the image build and the per-subtask rebuild, so the two cannot drift
# apart. cmake is re-run every time on purpose: `git clean -fdq` between subtasks removes
# any generated file the .gitignore does not name, and a stale cache is cheap to refresh
# next to the compile that follows it.
#
# ENABLE_WERROR is off. Tarantool's CI turns it on, but a gold patch that introduces a new
# warning would then fail to build and be scored as "does not reproduce" rather than as the
# bug fix it is.
RUN set -eux; \
    printf '%s\n' \
      '#!/bin/sh' \
      'set -eu' \
      'cd /tarantool' \
      'JOBS="${SWESWEEP_BUILD_JOBS:-4}"' \
      'cmake . -DCMAKE_BUILD_TYPE=RelWithDebInfo -DENABLE_WERROR=OFF' \
      'make -j"$JOBS"' \
      > /usr/local/bin/tarantool-build; \
    chmod +x /usr/local/bin/tarantool-build

RUN tarantool-build

CMD ["/tarantool/src/tarantool", "--version"]
