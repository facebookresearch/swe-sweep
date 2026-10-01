# Maximally-buggy V — frozen at the 0.3.4 release tag.
#
# Built upstream by `pandora construct build-image -t v@0.3.4`, which prepares the build context
# from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the V source tree at that tag
# into ./v, exports the two repos V's bootstrap needs into ./vc and ./tcc (declared as the
# base commit's `extra_trees`), and copies this file in as ./Dockerfile. The image holds
# the V git tree with a `baseline` commit+tag; the host-controlled evaluator
# (tasks/v/task.yaml) does `git reset --hard baseline`, then applies the per-bug
# test/gold patches and rebuilds.
#
# Four things are specific to a V task:
#
# 1. **V bootstraps out of two other repositories, and both are staged, not downloaded.**
#    `make` normally clones `vlang/vc` (the C translation of the compiler, regenerated on
#    every upstream commit) and `vlang/tccbin` (a prebuilt tcc) from GitHub at build time.
#    Doing that would make the image un-period-correct — it would bootstrap a 2023 compiler
#    out of today's `v.c` — and it needs network the builder may not have. Both are
#    therefore exported into the context at a commit contemporary with the anchor and
#    copied in, and `make local=1` is told to use what it finds instead of pulling.
#
# 2. **tcc is the C backend, deliberately.** V compiles a fresh C program for *every* test
#    file it runs, so the C compiler is the dominant cost of the whole census; tcc is
#    several times faster than gcc and is a configuration upstream's own CI runs
#    (`ubuntu-tcc`). The two `missing_c_lib_header_*` golden cases are the known price:
#    tcc has no `__has_include`, so their recorded diagnostics are gcc's. Upstream skips
#    them under tinyc for the same reason.
#
# 3. **The baseline commit has to be forced in.** V's .gitignore starts with `*/**/*` plus
#    `!*/` / `!*.*` — a deny-list of everything in a subdirectory, re-allowing only names
#    containing a dot — and separately ignores the bare name `v`, which is *also* the name
#    of the compiler's own source directory (`vlib/v/`). A plain `git add -A` therefore
#    commits a baseline with the entire compiler missing. `git add -A -f` is what makes the
#    baseline the real tree.
#
# 4. **`vc/` and `thirdparty/tcc/` are copied in after the baseline commit, on purpose.**
#    Both are gitignored upstream, so `git clean -fdq` between subtasks leaves them alone
#    and the bootstrap inputs survive every reset — but only if they are not *tracked*,
#    which the forced `git add -A -f` above would otherwise make them.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/vlang/v.git /src \
 && git -C /src checkout --quiet 0.3.4 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-extra-0
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/vlang/vc.git /src \
 && git -C /src checkout --quiet 4dfde7ce12b6e96b4f1f4303ebd184342037e1cd \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-extra-0: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-extra-1
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/vlang/tccbin.git /src \
 && git -C /src checkout --quiet 12f392c3d31ea6ca3cf14b9de576371792c0b9cd \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-extra-1: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM debian:bookworm
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# gcc is still needed: it links the bootstrap `v1.exe` from vc/v.c, and tcc only takes over
# once V itself is running. libgc/libatomic_ops are vendored under thirdparty/, so nothing
# else is required at build time.
ENV DEBIAN_FRONTEND=noninteractive
RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    echo 'Acquire::Retries "5";' >> /etc/apt/apt.conf.d/10sandbox; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        build-essential git ca-certificates \
        libssl-dev zlib1g-dev pkg-config xz-utils; \
    rm -rf /var/lib/apt/lists/*

# V source tree at the anchor tag, exported from the local clone into the build context.
COPY --from=swesweep-src /src /v
WORKDIR /v

# Make the exported tree a git repo, commit the source and tag it `baseline`. `-f` is
# mandatory here — see the header.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A -f && git commit -q -m "v maxbug source" && git tag baseline

# The bootstrap inputs, at commits contemporary with the anchor. After the baseline commit
# so that they stay untracked-and-ignored and survive `git clean`.
COPY --from=swesweep-extra-0 /src /v/vc
COPY --from=swesweep-extra-1 /src /v/thirdparty/tcc

# `local=1` stops the makefile pulling vc and tccbin from GitHub.
RUN set -eux; \
    make local=1; \
    ./v version; \
    ./thirdparty/tcc/tcc.exe -v

# One script for both the image build and the per-subtask rebuild, so the two cannot drift.
# `v self` is V's own self-compile: it rebuilds cmd/v with the current binary and swaps the
# result in, which is the only rebuild a gold patch in the compiler needs. A patch that
# only touches the standard library needs no rebuild at all — V recompiles vlib from source
# on every invocation — but rebuilding anyway keeps one code path.
RUN set -eux; \
    printf '%s\n' \
      '#!/bin/sh' \
      'set -eu' \
      'cd /v' \
      './v self' \
      > /usr/local/bin/v-build; \
    chmod +x /usr/local/bin/v-build

RUN v-build

# The golden `.out` expectations are recorded without colour, and V colourises when it
# thinks it has a terminal.
ENV VCOLORS=never

CMD ["/v/v", "version"]
