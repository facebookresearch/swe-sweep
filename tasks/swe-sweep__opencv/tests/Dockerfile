# Maximally-buggy OpenCV — frozen at candidate anchor version 4.0.1.
#
# Built upstream by `pandora construct build-image -t opencv@4.0.1`, which prepares the build
# context under data/opencv/maxbug/4.0.1/context/: it exports the OpenCV source tree at
# 4.0.1 FROM THE LOCAL CLONE (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md) into ./opencv, and copies this file in as
# ./Dockerfile.
#
# Why 4.0.1: OpenCV's bug-coverage curve peaks on 2018-12-13 at 228 live subtasks, and
# 4.0.1 (22 Dec 2018) is the release tag on that peak with 223 — tied with 3.4.4, 3.4.5
# and 4.0.0, and the newest of that set.
#
# Why focal: 4.0.1 is 2018 C++, and gcc 12 (bookworm) rejects it over headers it no
# longer includes transitively. Ubuntu 20.04 ships gcc 9, which is close enough to the
# period toolchain to build it unmodified.
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
 && git clone --quiet --no-checkout https://github.com/opencv/opencv.git /src \
 && git -C /src checkout --quiet 4.0.1 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-extra-0
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/opencv/opencv_extra.git /src \
 && git -C /src checkout --quiet 4.0.1 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-extra-0: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM ubuntu:20.04
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

ENV DEBIAN_FRONTEND=noninteractive
RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    echo 'Acquire::Retries "5";' >> /etc/apt/apt.conf.d/10sandbox; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        git cmake ninja-build g++ pkg-config ca-certificates \
        zlib1g-dev libjpeg-turbo8-dev libpng-dev libtiff-dev libwebp-dev \
        libavcodec-dev libavformat-dev libswscale-dev libavutil-dev \
        python3-dev python3-numpy python-is-python3; \
    rm -rf /var/lib/apt/lists/*
# Acquire::Retries is not belt-and-braces: this apt runs through FwdProxy, which returns
# an occasional 502 on a single .deb, and one failed fetch fails the whole build minutes
# in. The Python alias is retained for repository-owned tooling.

# OpenCV source tree at the candidate ref, exported from the local clone into the build
# context (see the header).
COPY --from=swesweep-src /src /opencv
# The sample data the gtest cases read, from the separate opencv_extra repo at the
# matching tag (the base commit's `extra_trees`). It is copied in OUTSIDE the repo, like
# the build tree, so `git reset --hard baseline` between subtasks cannot disturb it and it
# can never leak into an agent's extracted patch.
COPY --from=swesweep-extra-0 /src /opencv-extra
WORKDIR /opencv

# Make the exported tree a git repo (the export carries no .git), commit the source and
# tag it `baseline` — a SOURCE-ONLY tree, so an agent's extracted patch can never carry a
# build artifact. Nothing is built inside the tree: the build directory is /build,
# OUTSIDE the repo, so the consumers' `git reset --hard baseline && git clean -fdq`
# cannot touch it.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "opencv maxbug source" && git tag baseline

# Everything that would DOWNLOAD during configure is off. OpenCV's cmake fetches IPPICV,
# the face landmark data and ADE (G-API's dependency) from raw.githubusercontent.com,
# which Meta's egress filter blocks; a missing download does not fail the configure, it
# silently drops the feature, so they are turned off explicitly instead of left to fail
# quietly. The vendored 3rdparty/ copies (protobuf for dnn, zlib, libjpeg…) are in the
# export and need no network.
#
# BUILD_TESTS is the point of the image: it produces the per-module `opencv_test_<mod>`
# gtest binaries the runner selects cases out of. Perf tests, examples, apps and the
# docs are all off — none of them is a test the benchmark grades.
RUN cmake -S /opencv -B /build -G Ninja \
        -DCMAKE_BUILD_TYPE=Release \
        -DBUILD_TESTS=ON \
        -DBUILD_PERF_TESTS=OFF \
        -DBUILD_EXAMPLES=OFF \
        -DBUILD_DOCS=OFF \
        -DBUILD_opencv_apps=OFF \
        -DBUILD_JAVA=OFF \
        -DWITH_IPP=OFF \
        -DWITH_ADE=OFF \
        -DWITH_CUDA=OFF \
        -DWITH_OPENCL=OFF \
        -DWITH_GTK=OFF \
        -DWITH_QT=OFF \
        -DOPENCV_ENABLE_NONFREE=OFF \
    && cmake --build /build -j 16

# The gtest binaries live in /build/bin and load the shared libs from /build/lib.
# OPENCV_TEST_DATA_PATH is what every case resolves its samples against; a case that
# cannot find its data reports itself as skipped, which the runner counts as "not run"
# rather than as a pass.
ENV OPENCV_TEST_DATA_PATH=/opencv-extra/testdata \
    LD_LIBRARY_PATH=/build/lib \
    PYTHONPATH=/build/python_loader

CMD ["/build/bin/opencv_test_core", "--gtest_list_tests"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
