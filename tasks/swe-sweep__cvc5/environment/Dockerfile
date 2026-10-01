# Maximally-buggy cvc5 — frozen at a candidate anchor in the 1.0/1.1 line.
#
# Built upstream by `pandora construct build-image -t cvc5@<v>`, which prepares the build context
# from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the source tree at the
# candidate tag into ./cvc5 and copies this file in as ./Dockerfile. The image holds the
# tree with a `baseline` commit+tag; the host-controlled runner
# (tasks/cvc5/task.yaml) does `git reset --hard baseline`, then applies the
# per-bug test/gold patches.
#
# One Dockerfile serves every 1.0.x / 1.1.x candidate: nothing below names a version, and
# the whole line has the same build interface (`configure.sh` + CMake) and the same system
# dependencies.
#
# Why jammy: the base image is squeezed between two hard version bounds, and 22.04 is the
# only common distribution that satisfies both.
#
# - **CMake >= 3.21**, because `ctest --output-junit` is how every CTest adapter here reads
#   its verdicts, and that flag arrives in 3.21. Debian bullseye ships 3.18, so the suite
#   would produce no report at all.
# - **Python <= 3.10**, because cvc5 1.0.5 caps it: `find_package(Python 3.6...<3.10.999)`
#   in cmake/Helpers.cmake, and configure fails outright above it. Debian bookworm ships
#   3.11 (this image was written against bookworm first and failed exactly there).
#
# jammy is 3.10 and CMake 3.22, and is period-correct for the 2022–2024 candidate range
# besides.
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
 && git clone --quiet --no-checkout https://github.com/cvc5/cvc5.git /src \
 && git -C /src checkout --quiet cvc5-1.0.5 \
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
ENV DEBIAN_FRONTEND=noninteractive

# The dependency list is cvc5's own CI one (.github/actions/install-dependencies): GMP is
# the arithmetic backend, flex/libfl the parser generator's runtime, libedit the
# interactive shell's line editing (a regression asserts on the shell's behaviour, so
# leaving it out changes what the suite measures).
#
# The Python modules are load-bearing rather than convenience: the build *generates* code
# at configure time and checks for each module up front, so a missing one is a configure
# error, not a runtime surprise. The options generator reads its .toml definitions with
# `toml` up to 1.0.5 and with `tomli` from 1.0.8 (both are installed so one image serves
# the range), and `pyparsing` is what the RARE rewrite-rule compiler (src/rewriter/, from
# 1.0.8 on) parses with. python3-pexpect is what the interactive-shell regressions drive
# cvc5 with.
#
# autotools-dev is for a *download* the ANTLR3 build no longer manages — see the sed
# below the baseline commit.
#
# libgtest-dev is here to *stop* a download. cvc5's FindGTest takes a system GoogleTest
# whenever it finds one and otherwise builds release-1.10.0 from source — and that 2020
# release does not compile under GCC 11, which rejects `dummy may be used uninitialized`
# in gtest-death-test.cc while the vendored build has -Werror on. The distribution's
# GoogleTest is newer and already built, so the external project never runs.
#
# The JRE is for the *parser*, and it is only needed by part of this version range. Up to
# 1.0.5 the SMT-LIB parser is generated by ANTLR3, whose generator is a Java program:
# src/parser/CMakeLists.txt does `find_package(Java COMPONENTS Runtime REQUIRED)` and
# cmake refuses to configure without it. 1.0.8 replaced ANTLR3 with a flex/bison parser
# and dropped the requirement. It is installed unconditionally so that one Dockerfile
# still serves every candidate in the range.
RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        build-essential cmake git ca-certificates pkg-config \
        autotools-dev \
        libgmp-dev libedit-dev flex libfl-dev bison libgtest-dev libgmock-dev \
        default-jre-headless \
        wget curl patch \
        python3 python3-toml python3-tomli python3-pyparsing python3-pexpect \
        python3-setuptools python-is-python3; \
    rm -rf /var/lib/apt/lists/*

# cvc5 source tree at the candidate ref, exported from the local clone into the build
# context (see the header).
COPY --from=swesweep-src /src /cvc5
WORKDIR /cvc5

# Make the exported tree a git repo (the export carries no .git), commit the source and
# tag it `baseline` — a SOURCE-ONLY tree, so an agent's extracted patch can never carry a
# build artifact.
#
# This happens BEFORE the build, and the ordering is the point. `--auto-download` unpacks
# its dependencies into `/cvc5/deps`, i.e. *inside* the repository, which is unlike the
# other compiled tasks here. cvc5's own .gitignore lists `/deps/` and `/build/`, so those
# trees are neither committed now nor removed later: the consumers reset with
# `git reset --hard baseline && git clean -fdq`, and without `-x` that leaves ignored
# paths alone. Committing first is what makes the ignore rules apply to them.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "cvc5 maxbug source" && git tag baseline

# Bit rot in a 2021 build recipe, repaired for the length of the build only.
#
# Up to 1.0.5 the ANTLR3 dependency is built from source, and its external project first
# downloads a current `config.guess`/`config.sub` from git.savannah.gnu.org. Those URLs
# now answer 404, so the dependency cannot build and neither can the parser. The files
# are ordinary autoconf helpers and Debian ships them in autotools-dev, so the two URLs
# are pointed at the local copies instead.
#
# The edit is made AFTER the `baseline` commit and reverted immediately after the build,
# so the frozen tree the agent sees is byte-identical to upstream. That is safe because
# the download only ever happens once, here: the external project's stamps live in
# /build, and the runner's incremental rebuilds never revisit it.
RUN if [ -f cmake/FindANTLR3.cmake ]; then \
        sed -i \
            -e 's|https://git.savannah.gnu.org/cgit/config.git/plain/config.guess|file:///usr/share/misc/config.guess|' \
            -e 's|https://git.savannah.gnu.org/cgit/config.git/plain/config.sub|file:///usr/share/misc/config.sub|' \
            cmake/FindANTLR3.cmake; \
    fi

# Configure into /build, OUTSIDE the repository, so a reset cannot reach the build tree at
# all (`--name` takes an absolute path). The rest of the line is cvc5's own CI recipe:
#
# - `production` is the configuration its releases are built and tested in;
# - `--assertions` keeps the internal assertions compiled in. A large share of cvc5's
#   fixed defects *are* assertion failures, and their regressions are written to trip the
#   assertion — with them compiled out the test cannot fail before the gold patch, so the
#   census would silently lose that whole class of bug. cvc5 runs its regressions in this
#   configuration in CI too, so a release tag is green in it;
# - `--unit-testing` registers the GoogleTest half of the suite. A plain production build
#   does not build it, and every unit-test subtask would report no target;
# - `--auto-download` fetches the dependencies cvc5 vendors by download (CaDiCaL, SymFPU,
#   LibPoly, GoogleTest). This is the one step that needs the network, and it happens at
#   image-build time — the reproduce and eval containers run with `--network=none`.
#
# Not `--ninja`, deliberately. Under Ninja the pre-1.0 tree fails to build at all: its
# ANTLR3 external project declares only `libantlr3c.a` in BUILD_BYPRODUCTS while the
# parser links the `.so`, and Ninja — unlike Make — refuses a graph with an undeclared
# output ("no known rule to make deps/lib/libantlr3c.so"). Make is a little slower and
# builds every candidate in the range.
RUN ./configure.sh production \
        --auto-download \
        --assertions \
        --unit-testing \
        --statistics \
        --name=/build

# Build the solver and then the whole test suite, warm, so a subtask's rebuild is
# incremental: the gold patch recompiles the translation units it touched and relinks,
# instead of building cvc5 from scratch inside a per-subtask container.
RUN cmake --build /build -j "$(nproc)" \
    && cmake --build /build -j "$(nproc)" --target build-tests

# Put the tree back exactly as upstream left it (see the sed above). `git diff --exit-code`
# is the proof, not a courtesy: a frozen tree that silently differs from the tag would make
# every extracted patch wrong.
RUN git checkout -- cmake/FindANTLR3.cmake 2>/dev/null || true; \
    git diff --exit-code --quiet

# Prove the suite is green *before* any patch is applied. A pristine failure reads as
# `fails_pre_gold` for every subtask that touches it and would quietly inflate the census.
#
# `-L regress0` is the fast tier of the regression corpus (seconds per case, thousands of
# cases) and `-L unit` is the whole GoogleTest half; between them they exercise every
# component a fix could land in. The slower tiers (regress1 and up) are left to the eval
# runner's visible suite — running them here would add hours to the image build without
# testing anything the two tiers below do not already reach.
RUN ctest --test-dir /build -j "$(nproc)" --output-on-failure -L 'regress0|unit'

CMD ["/build/bin/cvc5", "--version"]
