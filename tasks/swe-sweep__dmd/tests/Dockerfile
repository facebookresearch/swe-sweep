# Maximally-buggy dmd — frozen at the v2.101.0 tag (2022-11-14).
#
# The same recipe as Dockerfile-2.105.0 with one value changed: the bootstrap compiler is
# the anchor's own release (note 1), so the release number appears in the .deb URL and a
# candidate needs its own file rather than a shared one. v2.101.0 is the first tag on the
# near side of the druntime merge (note 2) and the top of the coverage curve there.
#
# Built upstream by `pandora construct build-image -t dmd@2.101.0`, which prepares the build context
# from the local clone (no GitHub access — see docs/ai/010-design/005-style-conventions.md):
# it exports the source tree at that tag into ./dmd, exports Phobos at its matching tag into
# ./phobos (the base commit's `extra_trees`), and copies this file in as ./Dockerfile. The
# image holds the tree with a `baseline` commit+tag; the host-controlled evaluator
# (tasks/dmd/task.yaml) does `git reset --hard baseline`, applies the per-bug
# test/gold patches, and rebuilds.
#
# Four things are specific to a dmd task:
#
# 1. **dmd is written in D, so building it needs a D compiler.** The bootstrap compiler is
#    the *same release* as the anchor, installed from the upstream .deb — period-correct by
#    construction, and guaranteed to be able to build this tree, because it is the compiler
#    upstream shipped it with.
#
# 2. **Phobos is a different repository, and the tests need it built.** dmd's own build
#    assumes Phobos is a *sibling directory*: the `dmd.conf` the build generates points at
#    `../phobos` relative to the repo, and run.d's `PHOBOS_PATH` defaults to the same place.
#    So Phobos is exported to /phobos beside /dmd and nothing has to be told where it is.
#    Druntime does not need this — the repo absorbed it at v2.101.0, which is one reason the
#    shortlist stays on that side of the move.
#
# 3. **The build output is gitignored, which is what makes the rebuild incremental.** dmd
#    puts everything it builds under `generated/`, and `.gitignore` names that directory, so
#    the runner's `git reset --hard baseline` + `git clean -fdq` between subtasks leaves the
#    object tree standing. A leaf change to one compiler module is then a recompile and a
#    relink rather than a from-scratch build.
#
# 4. **A crashed compiler is a failing test, not a broken run.** An ICE is the commonest bug
#    shape here, and run.d reports it the same way as any other lost comparison — see the
#    `dmd-testsuite` suite adapter, which reads run.d's `>>> TARGET FAILED:` marker rather
#    than its exit code so the two stay distinguishable.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/dlang/dmd.git /src \
 && git -C /src checkout --quiet v2.101.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-extra-0
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/dlang/phobos.git /src \
 && git -C /src checkout --quiet v2.101.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-extra-0: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM debian:bookworm
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

ENV DEBIAN_FRONTEND=noninteractive

# The compiler's own build needs a C/C++ toolchain (the backend has C++ sources and every
# link goes through the system linker); runnable_cxx tests compile C++ beside the D; and
# std.net.curl loads libcurl at run time.
#
# **gdb is not optional here.** Fourteen corpus cases drive a real debugger to check the
# debug info dmd emits (`runnable/gdb*.d`, and `runnable/b18504.d`, which exits 127 without
# it). Without gdb they fail in the pristine image, which is the failure mode the census
# cannot survive: a case that already fails reads as `fails_pre_gold` for any subtask that
# touches it, and the visible-suite gate can never be green.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        build-essential gcc g++ binutils make git curl ca-certificates \
        gdb libcurl4 libxml2 xz-utils gnupg; \
    rm -rf /var/lib/apt/lists/*

# The bootstrap D compiler: the anchor's own release. `apt-get install ./…` rather than
# `dpkg -i` so the .deb's dependencies resolve in one step.
RUN set -eux; \
    curl -fsSL -o /tmp/dmd.deb \
        https://downloads.dlang.org/releases/2.x/2.101.0/dmd_2.101.0-0_amd64.deb; \
    apt-get update; \
    apt-get install -y --no-install-recommends /tmp/dmd.deb; \
    rm -rf /var/lib/apt/lists/* /tmp/dmd.deb; \
    dmd --version

# The two trees, as siblings — see note 2 in the header.
COPY --from=swesweep-src /src /dmd
COPY --from=swesweep-extra-0 /src /phobos
WORKDIR /dmd

# Make the exported tree a git repo (the export carries no .git), commit the source and tag
# it `baseline`. Before the build, so the whole `generated/` footprint stays untracked and
# ignored, and therefore survives the runner's reset between subtasks.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "dmd maxbug source" \
    && git tag baseline

# Phobos is not graded and is never patched, but it is a build input, so it gets the same
# treatment for reproducibility of the build itself.
RUN cd /phobos \
    && git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "phobos build input" \
    && git tag baseline

# One script for both the image build and the per-subtask rebuild, so the two cannot drift
# apart.
#
# Phobos is rebuilt every time even though no patch touches it: it links against druntime,
# which *is* in the graded tree, so a druntime fix that changes a layout would otherwise be
# tested against a stale libphobos2.a. It is the cheap half of the build.
#
# ENABLE_RELEASE is deliberately *off*. It buys build speed at the cost of turning the
# compiler's own asserts off, and those asserts are how a large class of dmd bugs surfaces
# at all — a release build turns an assertion failure into silently wrong code, which the
# corpus then does not catch.
RUN set -eux; \
    printf '%s\n' \
      '#!/bin/sh' \
      'set -eu' \
      'JOBS="${SWESWEEP_BUILD_JOBS:-4}"' \
      '# posix.mak is the one entry point that works across the anchor range: it is the' \
      '# real build up to 2.109 and a forwarder to the newer Makefile after that.' \
      'export HOST_DMD=/usr/bin/dmd' \
      'cd /dmd' \
      'make -f posix.mak -j"$JOBS" all' \
      'cd /phobos' \
      'make -f posix.mak -j"$JOBS"' \
      > /usr/local/bin/dmd-build; \
    chmod +x /usr/local/bin/dmd-build

RUN dmd-build

# The corpus runner builds its own helper tools on first use (d_do_test, the unit-test
# runner, …) and caches them under compiler/test/test_results, which .gitignore also names.
# Doing it here means a subtask's first `run.d` is only the test it was asked for.
#
# It doubles as the image's own smoke test: this must pass before any patch is applied, or
# the census reads a pristine failure as `fails_pre_gold` and fills up with subtasks that
# reproduce nothing.
# The image's own smoke test. Five cases, chosen rather than sampled:
#
# * one from each of the three graded categories, so all three ways a case can be judged
#   are covered — compiles clean, produces exactly these diagnostics, links and runs;
# * two that need **gdb**, because that is the dependency the pristine image was actually
#   missing (see docs/ai/040-experiments/dmd/) and the one a future edit is most likely to
#   drop again.
#
# The exhaustive version of this check — the whole ~3500-case corpus against the untouched
# tree — is a *one-off validation*, not a build step: it takes 67 seconds on a devserver
# and over half an hour on a Batch node, where thousands of small compile-and-link steps
# run against an overlay filesystem. It was run, it is clean, and the result is in the
# experiment record.
#
# `-j` is not tuning, it is a correctness knob: run.d defaults to *twice* the core count,
# and thirty-two concurrent dmd invocations — several of them linking — took a 64 GB
# builder out with the OOM killer.
RUN cd /dmd/compiler/test && ./run.d -j8 \
    compilable/99bottles.d fail_compilation/aacmp10381.d runnable/hello.d \
    runnable/gdb1.d runnable/b18504.d

CMD ["/dmd/generated/linux/release/64/dmd", "--version"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
