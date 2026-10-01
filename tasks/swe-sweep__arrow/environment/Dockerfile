# Maximally-buggy Apache Arrow — frozen at candidate anchor version 11.0.0.
#
# Built upstream by `pandora construct build-image -t arrow@11.0.0`, which prepares the build
# context under data/_remote_only/build_contexts/arrow/11.0.0/: it exports the arrow
# source tree at apache-arrow-11.0.0 FROM THE LOCAL CLONE (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md) into ./arrow, fills in the two git
# submodules from data/tasks/arrow/_local_only/submodules/ at the commits the ref pins,
# and copies this file in as ./Dockerfile.
#
# Why 11.0.0: arrow's bug-coverage curve peaks at 146 on 2023-01-26 and
# apache-arrow-11.0.0 (18 January 2023) carries 142 — within four of the maximum and a
# real release, where the two tags above it are a .dev marker and a patch release
# (docs/ai/040-experiments/arrow/260811-first-funnel-and-anchor.md).
#
# Why bookworm and not the period-correct Ubuntu 22.04: arrow 11 requires xsimd >= 8.1.0
# and jammy ships 7.6.0. Bookworm ships exactly 8.1.0, plus the thrift, protobuf and LLVM
# versions arrow 11 wants, and configures clean
# (docs/ai/040-experiments/arrow/260811-build-recipe-probe.md).
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
 && git clone --quiet --no-checkout https://github.com/apache/arrow.git /src \
 && git -C /src checkout --quiet apache-arrow-11.0.0 \
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

ENV DEBIAN_FRONTEND=noninteractive
# Every third-party dependency comes from the distro: arrow's default AUTO resolution
# DOWNLOADS the ones it cannot find, and the image build must not need egress of its own
# beyond apt. Acquire::Retries is not belt-and-braces — this apt runs through FwdProxy,
# which returns an occasional 502 on a single .deb, and one failed fetch fails the whole
# build minutes in.
RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    echo 'Acquire::Retries "5";' >> /etc/apt/apt.conf.d/10sandbox; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        git cmake ninja-build g++ pkg-config ca-certificates \
        python3 python3-dev python3-numpy python-is-python3 \
        libbrotli-dev libbz2-dev libgflags-dev libgoogle-glog-dev liblz4-dev \
        libre2-dev libsnappy-dev libssl-dev libthrift-dev thrift-compiler \
        libutf8proc-dev libzstd-dev rapidjson-dev zlib1g-dev \
        libgtest-dev libgmock-dev libxsimd-dev \
        libboost-system-dev libboost-filesystem-dev \
        libprotobuf-dev protobuf-compiler libprotoc-dev \
        llvm-14-dev clang-14 libclang-14-dev; \
    rm -rf /var/lib/apt/lists/*
# The Python alias is retained for repository-owned tooling.
#
# libprotoc-dev is named separately because gandiva links libprotoc and libprotobuf-dev
# does not pull it in.

# Debian's libxsimd-dev ships a cmake config whose INTERFACE_LINK_LIBRARIES names `xtl`.
# Nothing ever defines an xtl target, so cmake passes it through as a bare `-lxtl` and
# libarrow.so fails to link against a library that does not exist — xtl is header-only,
# there is no libxtl. Deleting the config is not an option either: arrow's SYSTEM
# resolution is find_package-only and then cannot find xsimd at all.
RUN sed -i 's/INTERFACE_LINK_LIBRARIES "xtl"/INTERFACE_LINK_LIBRARIES ""/' \
        /usr/lib/x86_64-linux-gnu/cmake/xsimd/xsimdTargets.cmake

# arrow source tree at the candidate ref, with its two test-data submodules, exported from
# the local clones into the build context (see the header).
COPY --from=swesweep-src /src /arrow
WORKDIR /arrow

# Make the exported tree a git repo (the export carries no .git), commit the source and
# tag it `baseline` — a SOURCE-ONLY tree, so an agent's extracted patch can never carry a
# build artifact. Nothing is built inside the tree: the build directory is /build,
# OUTSIDE the repo, so the consumers' `git reset --hard baseline && git clean -fdq`
# cannot touch it. The submodule trees are committed along with everything else, so the
# reset between subtasks keeps the test data in place.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "arrow maxbug source" && git tag baseline

# The C++ implementation is the graded product, so the cmake source dir is cpp/, not the
# repo root. Components on: the ones the anchor's subtasks actually touch — compute, csv,
# json, ipc, filesystem, dataset, parquet and gandiva (41 of 231 source-file hits, and the
# only reason LLVM is here). Off: the allocators, S3, flight, substrait, ORC and the
# microbenchmarks, none of which the population needs and each of which costs build time
# or another dependency.
RUN cmake -S /arrow/cpp -B /build -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DARROW_DEPENDENCY_SOURCE=SYSTEM \
        -DARROW_BUILD_TESTS=ON \
        -DARROW_BUILD_BENCHMARKS=OFF \
        -DARROW_BUILD_EXAMPLES=OFF \
        -DARROW_BUILD_INTEGRATION=OFF \
        -DARROW_COMPUTE=ON \
        -DARROW_CSV=ON \
        -DARROW_JSON=ON \
        -DARROW_IPC=ON \
        -DARROW_FILESYSTEM=ON \
        -DARROW_DATASET=ON \
        -DARROW_PARQUET=ON \
        -DARROW_GANDIVA=ON \
        -DARROW_JEMALLOC=OFF \
        -DARROW_MIMALLOC=OFF \
        -DARROW_S3=OFF \
        -DARROW_FLIGHT=OFF \
        -DARROW_SUBSTRAIT=OFF \
        -DARROW_ORC=OFF \
        -DARROW_WITH_BROTLI=ON \
        -DARROW_WITH_BZ2=ON \
        -DARROW_WITH_LZ4=ON \
        -DARROW_WITH_SNAPPY=ON \
        -DARROW_WITH_ZLIB=ON \
        -DARROW_WITH_ZSTD=ON \
        -DARROW_WITH_UTF8PROC=ON \
        -DARROW_WITH_RE2=ON \
        -DARROW_USE_CCACHE=OFF \
    && cmake --build /build -j 32

# A Release build puts every test binary in one flat directory, /build/release/, all named
# <component>-…-test — which is what lets the runner run them all under one
# --gtest_filter instead of mapping a patched file to its binary (arrow's
# add_arrow_test() groups several *_test.cc into one executable, so the path cannot name
# it). The test data lives in the two submodules; the tests find it through these env
# vars and skip, rather than fail, without them.
ENV ARROW_TEST_DATA=/arrow/testing/data \
    PARQUET_TEST_DATA=/arrow/cpp/submodules/parquet-testing/data

CMD ["sh", "-c", "ls /build/release/*-test | head"]
