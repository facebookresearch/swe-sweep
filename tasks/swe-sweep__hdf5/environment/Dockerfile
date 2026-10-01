# Maximally-buggy hdf5 — frozen at anchor version 1.10.8.
#
# Built upstream by `pandora construct build-image -t hdf5@1.10.8`, which prepares the build
# context from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the source tree at
# `hdf5-1_10_8` into ./hdf5 and copies this file in as ./Dockerfile.
#
# Why 1.10.8: hdf5's coverage curve peaks in January 2021 at 70 live subtasks, but almost
# none of the patches graft that far back — at `hdf5-1_10_7` the count of subtasks whose
# test *and* gold patch apply is zero, and at `hdf5-1_8_22` it is five. The intersection
# of live and applying peaks at 1.10.8 instead, which also leaves the largest
# live-but-not-applying set for `rebase-patch` to work on. See
# docs/ai/040-experiments/hdf5/260824-anchor-choice.md.
#
# Why bookworm and not the era-correct bullseye: CTest only grew `--test-dir` in CMake
# 3.20, and bullseye ships 3.18. Passing it there does not fail — ctest ignores it, runs in
# the current directory, prints "No tests were found!!!" and **exits 0**, so the gate below
# passes without testing anything and every runner invocation collects nothing. Every ctest
# adapter in this repo drives the suite with `--test-dir`, so the image has to be new enough
# to honour it.
#
# Built at Meta through FwdProxy: `pandora construct build-image` wraps the build in
# `sudo with-proxy` with `--network=host`, and apt's unprivileged `_apt` sandbox user
# cannot read a proxied download — so apt is told to run as root before it touches the
# network (see docs/ai/030-debug/260626-maxbug-image-registry-blocked.md).
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/HDFGroup/hdf5.git /src \
 && git -C /src checkout --quiet hdf5-1_10_8 \
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
        git cmake make gcc g++ perl \
        zlib1g-dev \
        bash diffutils ca-certificates; \
    rm -rf /var/lib/apt/lists/*
# diffutils is load-bearing, not a convenience: the tool tests are shell-driven
# comparisons that diff a written file's dump against a recorded expectation, and without
# `diff` they degrade instead of failing.

COPY --from=swesweep-src /src /hdf5
WORKDIR /hdf5

# Make the exported tree a git repo (the export carries no .git), commit the sources and
# tag them `baseline` — a SOURCE-ONLY tree, so an agent's extracted patch can never carry
# a build artifact. Nothing is built inside the tree: /build sits OUTSIDE the repo, so the
# runner's `git reset --hard baseline && git clean -fdq` cannot touch it and the
# incremental rebuild survives between subtasks.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "hdf5 maxbug source" && git tag baseline

# Configure and build once, so a subtask's rebuild is incremental. The runner
# reconfigures the same /build on every run — a test patch can register a new CTest case,
# and an already-configured tree does not know about it until cmake re-reads the file.
#
# **Only the C library and its high-level wrappers are built.** 153 of the 221
# skim-accepted subtasks put their test in `test/` and 4 more in `hl/test/`; the C++,
# Fortran and Java bindings account for 20 between them and each one is a separate
# toolchain and a separate suite. Parallel (`testpar/`, 25 subtasks) needs an MPI runtime
# the census container has no business starting. Those subtasks report "no targets" rather
# than failing, and the census numbers must be read with that in mind.
#
# ALLOW_UNSUPPORTED is required to build the tools against a thread-unsafe library, and
# the deflate filter is on because a large share of the dataset tests write compressed
# chunks and silently skip without it — a skipped test cannot express a fail→pass.
#
# **cmake is run from inside /build, and that is load-bearing.** hdf5 determines the
# maximum decimal precision with a `try_run` whose program writes `pac_Cconftest.out` into
# its own working directory — inherited from the `cmake` process — and then reads it back
# from `${CMAKE_BINARY_DIR}`. Every upstream recipe does `cd build && cmake ..`, so the two
# coincide; configuring from the source tree drops the file in /hdf5 and configure aborts
# with "file failed to open for reading: /build/pac_Cconftest.out". The runner reconfigures
# from /build for the same reason.
RUN mkdir -p /build && cd /build && cmake -S /hdf5 -B /build \
        -DCMAKE_BUILD_TYPE=Release \
        -DBUILD_TESTING=ON \
        -DBUILD_SHARED_LIBS=OFF \
        -DHDF5_BUILD_HL_LIB=ON \
        -DHDF5_BUILD_TOOLS=ON \
        -DHDF5_BUILD_CPP_LIB=OFF \
        -DHDF5_BUILD_FORTRAN=OFF \
        -DHDF5_BUILD_JAVA=OFF \
        -DHDF5_BUILD_EXAMPLES=OFF \
        -DHDF5_ENABLE_PARALLEL=OFF \
        -DHDF5_ENABLE_Z_LIB_SUPPORT=ON \
        -DHDF5_ENABLE_SZIP_SUPPORT=OFF \
        -DALLOW_UNSUPPORTED=ON \
    && cmake --build /build -j "$(nproc)"

# Prove the suite is green *before* any patch is applied. A pristine failure reads as
# `fails_pre_gold` for every subtask that targets the same case and would quietly inflate
# the whole census. `H5TEST-testhdf5-base` is the aggregate case two dozen of the graded
# sources compile into, so it is the one that matters most; `H5TEST-dsets` is the single
# largest standalone program and covers the chunked/filtered paths the deflate option
# above exists for.
# `--no-tests=error` is not decoration: a selector that matches nothing is not an error to
# ctest, so without it a gate whose regex has gone stale reports success having run zero
# tests — which is exactly how this image passed its first build.
RUN ctest --test-dir /build --output-on-failure --no-tests=error \
        -R '^H5TEST-(testhdf5-base|testhdf5-clear-objects|dsets)$'

CMD ["/build/bin/h5dump", "--version"]
