# Maximally-buggy Idris 2, frozen at the v0.5.1 release tag (2021-09-20) — the anchor.
#
# Why v0.5.1: the coverage curve peaks on 2021-09-24 at 65 live subtasks, two days after
# this tag, and v0.5.1 itself carries 64. Every later tag is worth much less (v0.6.0 49,
# v0.7.0 34), and the earlier ones less again (v0.4.0 55). See
# docs/ai/040-experiments/idris2/.
#
# Built upstream by `pandora construct build-image -t idris2@0.5.1`, which prepares the build
# context from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the Idris 2 source tree at that
# tag into ./idris2 and copies this file in as ./Dockerfile. The image holds the tree with
# a `baseline` commit+tag; the host-controlled evaluator
# (tasks/idris2/task.yaml) does `git reset --hard baseline`, applies the per-bug
# test/gold patches and rebuilds.
#
# Three things are specific to a self-hosted compiler:
#
# 1. **The compiler is written in itself, so the image has to bootstrap.** `make bootstrap`
#    compiles the checked-in generated Chez Scheme under bootstrap/ into a throwaway
#    `idris2-boot`, uses it to build the real compiler, and then rebuilds everything with
#    that. Only the last stage's output is kept in build/, and it is that build/ which
#    makes every later per-subtask rebuild incremental: Idris 2's .gitignore covers
#    `/build` and `/libs/**/build`, so the `git clean -fdq` between subtasks leaves the
#    .ttc cache alone.
#
# 2. **The per-subtask rebuild needs an *unpatched* compiler to compile the patched one.**
#    That is what the installation under /root/.idris2 is: the baseline compiler, out of the
#    way of the build tree, and passed back in as IDRIS2_BOOT. Rebuilding the compiler with
#    itself after the fix has been applied would be a different experiment.
#
# 3. **Only the Chez backend is installed.** The corpus also covers the Racket, Gambit and
#    Node code generators; Test.Golden declares those pools' Requirements and skips them
#    when the tool is absent, so those cases report "no targets" rather than failing. Their
#    subtasks are out of scope for this image, by choice — installing four more runtimes
#    would multiply the image size for a small tail of the population.
#
# Debian bullseye, not a newer release: its chezscheme is 9.5.4 and its gcc is 10, which is
# the toolchain of 2021 that this tree was released against, and the Chez is built with
# threading support — which `make bootstrap` checks for and refuses to proceed without.
# (Idris 2's own bootstrap CI deliberately runs on the *LTS* Chez for the same reason: the
# generated scheme under bootstrap/ is written against the older runtime.)
#
# Built at Meta through FwdProxy: `pandora construct build-image` wraps the build in
# `sudo with-proxy` with `--network=host`, and apt's unprivileged `_apt` sandbox user
# cannot read a proxied download — so apt is told to run as root before it touches the
# network (see docs/ai/030-debug/260626-maxbug-image-registry-blocked.md).
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/idris-lang/Idris2.git /src \
 && git -C /src checkout --quiet v0.5.1 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM debian:bullseye
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

ENV DEBIAN_FRONTEND=noninteractive
RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    echo 'Acquire::Retries "5";' >> /etc/apt/apt.conf.d/10retries; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        build-essential chezscheme git make \
        libgmp-dev coreutils ca-certificates; \
    rm -rf /var/lib/apt/lists/*

# The corpus is UTF-8 — Idris 2 source and its recorded output both use unicode operators
# and box-drawing characters in error messages. Under the default C locale the golden
# comparison sees mojibake on both sides and a large slice of the corpus fails at the
# baseline, which would read as a repo where everything reproduces.
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8

# Idris 2 source tree at the anchor tag, exported from the local clone into the build
# context (see the header).
COPY --from=swesweep-src /src /idris2
WORKDIR /idris2

# Make the exported tree a git repo (the export carries no .git), commit the source and tag
# it `baseline`.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "idris2 maxbug source" && git tag baseline

# `scheme` is what the Debian package calls the Chez executable, and what Idris 2's own CI
# passes as SCHEME.
ENV SCHEME=scheme

# Stage 1+2 of the bootstrap, then install the result as the *baseline* compiler. Nothing
# later rebuilds the installed one — it is the fixed point every subtask's rebuild starts
# from.
RUN make bootstrap SCHEME=scheme

# `make install` with **no PREFIX override**, on purpose. The prefix the compiler was
# built with is baked into it (Makefile writes `yprefix` into src/IdrisPaths.idr) and is
# where it looks for its data files and its libraries at run time. Installing anywhere
# else splits the installation in two: `install-support` obeys ${PREFIX} because it is a
# shell copy, but `install-libs` runs `idris2 --install`, which obeys the *compiler's* own
# prefix — so the libraries land in one tree and the Chez support files in the other, and
# the first thing that uses the installed compiler dies with
#   INTERNAL ERROR: Can't find data file chez/support.ss
# The default prefix is the baked one, so leaving it alone is what keeps them together.
RUN make install
ENV PATH=/root/.idris2/bin:$PATH

# One script for the per-subtask rebuild. `make all` rebuilds the compiler from the patched
# sources using the baseline compiler and then rebuilds the libraries with the result;
# both are incremental against the .ttc cache the image build left behind. Idris 2's own
# build is single-threaded (the work happens inside one `idris2 --build`), so
# SWESWEEP_BUILD_JOBS is not passed to make — it is the test runner's thread count.
RUN set -eux; \
    printf '%s\n' \
      '#!/bin/sh' \
      'set -eu' \
      'cd /idris2' \
      'make all IDRIS2_BOOT=/root/.idris2/bin/idris2 SCHEME=scheme' \
      > /usr/local/bin/idris2-build; \
    chmod +x /usr/local/bin/idris2-build

# The one entry point the host-side IdrisGoldenSuite calls. It exists so the suite never
# has to reproduce what `make test` sets up — all three of these are version-specific and
# would otherwise have to be duplicated (and kept in step) on the host:
#
#  - `testenv` installs the runtime support into the test prefix, links each freshly built
#    library's build/ttc into it, and **rebuilds the runtests driver** — without which a
#    case added by a test patch is invisible in the trees whose tests/Main.idr still lists
#    its pools by hand;
#  - IDRIS2_PREFIX is a make variable (TEST_PREFIX) and is *not* exported, so the recipe
#    has to put it into runtests' environment itself;
#  - NAME_VERSION the main Makefile does export, and tests/testutils.sh builds every
#    library search path from it — unset, every case fails on a missing Prelude.
#
# `include Makefile` rather than a copy of its values: they then come from the anchor's own
# tree, so one recipe fits every candidate version.
#
# --interactive is deliberately not passed. The repository's own `make test` passes it, and
# under it a failing case stops to ask whether to overwrite the golden file; with no tty
# that is an immediate hang rather than a verdict.
#
# SWESWEEP_ONLY is **one** case name, never a list. The two eras of `--only` disagree about
# how they take several: the 0.5 driver takes every remaining argument, the 0.7 one takes a
# single space-separated argument and then keeps parsing. A single unquoted name is the
# only form both read the same way, and the suite loops.
#
# `swesweep-testenv` is separate from `swesweep-run` so a run that selects several cases pays
# for the prefix install and the driver rebuild once, not once per case.
RUN set -eux; \
    mkdir -p /usr/local/share/swesweep; \
    { \
      printf '%s\n' 'include Makefile'; \
      printf '%s\n' 'SWESWEEP_ONLY ?='; \
      printf '%s\n' 'SWESWEEP_THREADS ?= 4'; \
      printf '%s\n' '.PHONY: swesweep-testenv swesweep-run'; \
      printf '%s\n' 'swesweep-testenv: testenv'; \
      printf '%s\n' 'swesweep-run:'; \
      printf '\t%s\n' '@cd tests && IDRIS2_PREFIX=$(TEST_PREFIX) ./build/exec/runtests $(TARGET) --threads $(SWESWEEP_THREADS) $(if $(SWESWEEP_ONLY),--only $(SWESWEEP_ONLY),)'; \
    } > /usr/local/share/swesweep/tests.mk

# Prove the environment before any patch is applied. A pristine failure here reads
# downstream as `fails_pre_gold` and would quietly inflate the census with subtasks that
# reproduce nothing, so it is a build error instead: this case must pass in the untouched
# tree, and running it also warms `testenv` so the first subtask does not pay for it.
RUN make -f /usr/local/share/swesweep/tests.mk swesweep-testenv; \
    make -f /usr/local/share/swesweep/tests.mk swesweep-run \
        SWESWEEP_ONLY=idris2/basic001 SWESWEEP_THREADS=4 \
    | tee /tmp/smoke.txt; \
    grep -q "^1/1 tests successful" /tmp/smoke.txt

# Exercise the per-subtask rebuild once, here, where a failure is a build error instead of
# 290 subtasks reporting "build failed after gold patch" an hour into a census. This is the
# step that catches a baseline compiler that cannot find its own data files, and it is
# nearly free: with nothing patched it is an incremental no-op that only relinks.
RUN idris2-build

CMD ["idris2", "--version"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
