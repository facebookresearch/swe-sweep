# Maximally-buggy jerryscript — frozen at candidate anchor version v2.2.0.
#
# Built upstream by `pandora construct build-image -t jerryscript@v2.2.0`, which prepares the build
# context from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the source tree at v2.2.0 into
# ./jerryscript and copies this file in as ./Dockerfile. The image holds the tree with a
# `baseline` commit+tag; the host-controlled evaluator
# (tasks/jerryscript/task.yaml) does `git reset --hard baseline`, then applies
# the per-bug test/gold patches.
#
# Why v2.2.0: it is the released tag nearest the coverage peak — 84 live subtasks against
# the curve's maximum of 106 two months later, and against 73 at v2.0 and 72 at v2.3.0.
# See docs/ai/040-experiments/260823-lang-runtimes-seed.md.
#
# Why gcc-9 and not the base image's gcc-10: jerryscript compiles with `-Werror` and a
# long list of `-Werror=<warning>`, so the *compiler version is part of the source
# contract* — every warning a newer gcc learns to emit is a build failure. gcc-9 is
# contemporary with this tag (2019) and is packaged in bullseye, whose archive is still
# served; buster's gcc-8 would be more exact but only from archive.debian.org.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/jerryscript-project/jerryscript.git /src \
 && git -C /src checkout --quiet v2.2.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM docker.io/library/debian:bullseye
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        gcc-9 g++-9 libc6-dev make cmake git ca-certificates python3 python-is-python3; \
    rm -rf /var/lib/apt/lists/*
# The Python alias is retained only for repository-owned tooling; benchmark control runs on the host.

# Pin the compiler for every later reconfigure too. The suite re-runs `cmake -S … -B
# /build` on each subtask (a test patch that adds a unit test also adds its filename to a
# CMakeLists, which an already-configured tree does not see), and the cached compiler in
# /build would be authoritative — but a rebuild from a wiped tree must not silently fall
# back to gcc-10 and start failing on -Werror.
ENV CC=gcc-9 \
    CXX=g++-9

# jerryscript source tree at the candidate ref, exported from the local clone into the
# build context (see the header).
COPY --from=swesweep-src /src /jerryscript
WORKDIR /jerryscript

# Make the exported tree a git repo (the export carries no .git) and tag it `baseline`.
# /build is outside the repo, so the consumers' `git reset --hard baseline && git clean
# -fdq` leaves the warm build tree alone: every subtask starts from pristine sources and
# recompiles only what its patch touched.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "jerryscript maxbug source" && git tag baseline

# Warm build. UNITTESTS=ON is what adds tests/unit-core and tests/unit-ext to the tree —
# without it the C half of the suite has no targets at all — and JERRY_CMDLINE=ON builds
# the `jerry` binary that every script case is run by.
#
# ENABLE_LTO=OFF for two reasons. jerryscript turns LTO on by default and then switches
# the archiver to a bare `gcc-ar`, which Debian ships only as the versioned `gcc-ar-9`, so
# the static libraries fail to link at all. And a census rebuilds this tree once per
# subtask: link-time optimisation would redo whole-program analysis every time, for a
# binary whose only job is to run a test.
#
# These are exactly the flags the runner's own reconfigure passes
# (tasks/jerryscript/task.yaml), so the cache it inherits is the one it would
# have built itself.
RUN cmake -S /jerryscript -B /build -DUNITTESTS=ON -DJERRY_CMDLINE=ON -DENABLE_LTO=OFF \
    && cmake --build /build -j "$(nproc)"

# Prove the suite is green *before* any patch is applied. A pristine failure reads as
# `fails_pre_gold` for every subtask and would quietly inflate the whole census. Both
# kinds of case are checked, because both are patch targets:
#   - a script that must be accepted (exit 0),
#   - a script under tests/jerry/fail/ that must be rejected (exit 1) — the inversion the
#     suite adapter encodes, and the one that would silently fail every such case,
#   - a compiled unit program (exit 0).
RUN set -eux; \
    /build/bin/jerry --call-on-exit __checkAsync tests/jerry/and-or.js; \
    ! /build/bin/jerry --call-on-exit __checkAsync tests/jerry/fail/arguments-assignment-strict.js; \
    /build/tests/unit-test-api

CMD ["/build/bin/jerry", "--version"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
