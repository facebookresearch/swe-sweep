# Maximally-buggy Lean 4 — the 4.x candidate anchors.
#
# One file for the whole shortlist: nothing below is version-specific. `stage0/` carries
# the bootstrap as generated C (point 1), so no period-correct toolchain has to be found
# and the same Ubuntu builds any 4.x tag; the tag is carried by the exported tree, not by
# this file.
#
# Built upstream by `pandora construct build-image -t lean4@<v>`, which prepares the build context
# from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the tree at that tag into ./lean4
# and copies this file in as ./Dockerfile. The image holds the tree with a `baseline`
# commit+tag; the host-controlled evaluator (tasks/lean4/task.yaml) does
# `git reset --hard baseline`, applies the per-bug test/gold patches, and rebuilds.
#
# Four things are specific to a Lean 4 task:
#
# 1. **The bootstrap is in the tree, so nothing period-correct has to be installed.**
#    `stage0/` is machine-generated C emitted by the previous compiler; cmake builds it
#    first and then uses it to build stage1 from `src/`. A plain Ubuntu with clang, cmake
#    and GMP is therefore the whole toolchain, and `stage0/` is not graded (see task.yaml).
#
# 2. **The build is out-of-source under `build/`, which `.gitignore` covers.** That is what
#    lets the runner's `git reset --hard baseline` + `git clean -fdq` leave the object tree
#    standing between subtasks, so a subtask's rebuild is incremental.
#
# 3. **cmake has to be re-run for every subtask, not just make.** The test corpus is
#    registered by globbing at *configure* time — `file(GLOB LEANRUNTESTS
#    tests/lean/run/*.lean)` in src/shell/CMakeLists.txt, one `add_test` per file — so a
#    test patch that adds a new test file registers nothing until cmake runs again. Both
#    steps live in one script so the image build and the per-subtask rebuild cannot drift.
#
# 4. **A Lean change invalidates a lot.** Touching `src/Lean/**` recompiles that module and
#    everything downstream of it in stage1; touching `src/kernel/**` or `src/runtime/**`
#    relinks the shared library the whole standard library was built against. The build
#    timeout in task.yaml is set for that, not for a leaf edit.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/leanprover/lean4.git /src \
 && git -C /src checkout --quiet v4.8.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM ubuntu:22.04
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

ENV DEBIAN_FRONTEND=noninteractive
# apt cannot reach FwdProxy as its unprivileged sandbox user on the devserver — see
# docs/ai/030-debug/260822-crystal-image-apt-sandbox.md.
RUN printf 'APT::Sandbox::User "root";\n' > /etc/apt/apt.conf.d/99sandbox
# Exactly upstream's own list from doc/make/ubuntu.md, plus the shell utilities the test
# driver (tests/lean/test_single.sh) shells out to.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        git libgmp-dev cmake ccache clang make \
        bash diffutils coreutils binutils ca-certificates; \
    rm -rf /var/lib/apt/lists/*

COPY --from=swesweep-src /src /lean4
WORKDIR /lean4

# Make the exported tree a git repo (the export carries no .git), commit the source and tag
# it `baseline`. Before the build, so the whole `build/` footprint stays untracked and
# ignored and therefore survives the runner's reset between subtasks.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "lean4 maxbug source" && git tag baseline

# Lean's golden files are UTF-8 and its test driver compares them byte for byte.
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8

# One script for the image build and the per-subtask rebuild both. cmake is re-run every
# time on purpose — see point 3 in the header.
RUN set -eux; \
    printf '%s\n' \
      '#!/bin/sh' \
      'set -eu' \
      'cd /lean4' \
      'JOBS="${SWESWEEP_BUILD_JOBS:-4}"' \
      'mkdir -p build/release' \
      'cd build/release' \
      'cmake ../.. -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++' \
      'make -j"$JOBS"' \
      > /usr/local/bin/lean4-build; \
    chmod +x /usr/local/bin/lean4-build

RUN lean4-build && /lean4/build/release/stage1/bin/lean --version

CMD ["/lean4/build/release/stage1/bin/lean", "--version"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
