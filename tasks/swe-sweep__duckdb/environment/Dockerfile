# Maximally-buggy duckdb — frozen at anchor version v0.10.0.
#
# Built upstream by `pandora construct build-image -t duckdb@v0.10.0`, which prepares the build
# context from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the source tree at v0.10.0 into
# ./duckdb and copies this file in as ./Dockerfile. The image holds the tree with a
# `baseline` commit+tag; the host-controlled evaluator (tasks/duckdb/task.yaml)
# does `git reset --hard baseline`, then applies the per-bug test/gold patches.
#
# Why v0.10.0: duckdb's coverage curve is unusually flat (257–329 live subtasks at every
# tag from v0.8.0 to v1.5.0), so it cannot pick the anchor — what picks it is how many
# patches still apply. Both halves apply for 189 subtasks here, against 173 at v1.1.0,
# 157 at v0.9.0 and at v1.4.2, and 155 at v1.2.2.
#
# Why Ubuntu 22.04: v0.10.0 is February 2024 and its CI ran on ubuntu-20.04/22.04 with the
# distribution GCC. 22.04's gcc-11 and cmake 3.22 are what that tree expects; a newer
# toolchain warns its way into errors on the vendored third_party/ sources.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/duckdb/duckdb.git /src \
 && git -C /src checkout --quiet v0.10.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM ubuntu:22.04
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# Built at Meta through FwdProxy: `pandora construct build-image` wraps the build in
# `sudo with-proxy` with `--network=host`, and apt's unprivileged `_apt` sandbox user cannot
# read a proxied download — so apt is told to run as root before it touches the network (see
# docs/ai/030-debug/260626-maxbug-image-registry-blocked.md).
#
# ninja rather than make: every subtask recompiles the tree after a patch, and ninja's
# incremental relink of one changed translation unit is what keeps that affordable.
RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    export DEBIAN_FRONTEND=noninteractive; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        build-essential cmake ninja-build git ca-certificates python3 pkg-config; \
    ln -sf /usr/bin/python3 /usr/local/bin/python; \
    rm -rf /var/lib/apt/lists/*

# Host-driven evaluation supplies complete commands.
ENTRYPOINT []

# The extension set duckdb's own CI builds for its test jobs (.github/workflows/Main.yml).
# It matters for the census and not just for fidelity: a sqllogictest that opens with
# `require parquet` is *skipped* when the extension is absent, and a skipped test can never
# reproduce anything — those subtasks would silently read as "does not fail pre-gold".
# jemalloc is deliberately left out: swapping the allocator buys nothing here and its
# failure modes are not the ones we are trying to measure.
#
# Set as ENV rather than only on the build line so the per-subtask rebuild
# (tasks/duckdb/task.yaml) configures cmake identically. A different set would
# make cmake reconfigure and throw the warm build tree away.
ENV BUILD_ICU=1 \
    BUILD_INET=1 \
    BUILD_PARQUET=1 \
    BUILD_TPCH=1 \
    BUILD_TPCDS=1 \
    BUILD_FTS=1 \
    BUILD_JSON=1 \
    BUILD_EXCEL=1 \
    GEN=ninja

COPY --from=swesweep-src /src /repo
WORKDIR /repo

# Two tags on the one commit, and the order matters. `baseline` is what the evaluator
# resets to. `v0.10.0` is **annotated** because duckdb's CMakeLists derives DUCKDB_VERSION
# from `git describe --tags --abbrev=0`, and git prefers an annotated tag over a lightweight
# one at the same commit — without it the engine reports its version as "baseline" and
# every test that asserts a version string fails at the baseline.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "duckdb maxbug source" \
    && git tag baseline \
    && git tag -a v0.10.0 -m "duckdb v0.10.0"

# The one expensive step: build the engine and the Catch2 `unittest` binary once, so a
# subtask's rebuild is incremental. `make release` re-runs cmake (cheap, and needed because
# a test patch may add a C++ case to a CMakeLists) and then drives ninja.
RUN CMAKE_BUILD_PARALLEL_LEVEL="$(nproc)" make release

# Prove the suite is green *before* any patch is applied. A pristine failure reads as
# `fails_pre_gold` for every subtask and would quietly inflate the whole census; catching it
# at image-build time is the cheapest place. Three files, one per shape the suite has: a
# plain sqllogictest, one that needs an extension (so the extension set above is checked
# too), and the C++ Catch2 side.
RUN ./build/release/test/unittest \
        "test/sql/aggregate/aggregates/test_sum.test" \
        "test/sql/copy/parquet/bigdecimal.test" \
    && ./build/release/test/unittest "[api]"

CMD ["./build/release/duckdb", "-c", "pragma version"]
