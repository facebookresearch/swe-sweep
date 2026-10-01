# Maximally-buggy Agda — frozen at master c9c20bf3683f (2021-08-17), the peak of the
# coverage curve (137 live subtasks) and the best patch-apply rate of the shortlist.
#
# Built upstream by `pandora construct build-image -t agda@2.6.3-dev-20210817`, which prepares the
# build context from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the Agda source tree at that
# commit into ./agda and copies this file in as ./Dockerfile. The image holds the Agda git
# tree with a `baseline` commit+tag; the host-controlled evaluator
# (tasks/agda/task.yaml) does `git reset --hard baseline`, then applies the
# per-bug test/gold patches and rebuilds.
#
# **Why a master commit and not a release tag.** Agda's release ritual strips the
# test-suite section out of Agda.cabal before tagging and reverts it on the next commit, so
# at v2.6.2, v2.6.4.3 and every other release tag there is no `agda-tests` component to
# build and the golden corpus is unreachable. Every candidate here is therefore a master
# commit.
#
# Three more things are specific to a Haskell task:
#
# 1. **The build is the expensive part, and it happens per subtask.** Agda is ~450 Haskell
#    modules and the gold patch always lands in them, so every subtask pays for an
#    incremental `cabal build`. The image builds once and keeps `dist-newstyle/` — which
#    Agda's own .gitignore covers as `dist-*/`, so the `git clean -fdq` between subtasks
#    leaves it alone and the rebuild stays incremental. Optimisation is off (`-O0`): a fix
#    to a leaf module then rebuilds in a couple of minutes instead of tens, and the golden
#    corpus is small enough that a slower `agda` still finishes inside the test timeout.
#
# 2. **Hackage is pinned by index state, not by luck.** A Haskell build resolves its whole
#    dependency tree from a snapshot of Hackage, so without `--index-state` the image stops
#    being period-correct the day someone uploads a new version.
#
# 3. **The binaries are copied out of the build tree, so the data directory must be told
#    where it is.** Cabal's generated `Paths_Agda` points at an install prefix that does not
#    exist here; `Agda_datadir` is the escape hatch it honours, and it has to point at the
#    primitive library in the source tree or every test fails on a missing `Agda.Builtin`.
#
# At this commit `agda-tests` is a `test-suite`, not an executable (it became one in
# September 2021), so the build needs `--enable-tests` and addresses it as
# `test:agda-tests`.
#
# GHC 8.10.7 is the compiler, installed with ghcup on Debian bullseye rather than taken
# from the matching `haskell` image.
#
# It is 8.10 and not 9.0 because the compiler has to agree with the Hackage snapshot. GHC
# 9.0.2 shipped `ghc-bignum-1.1` in December 2021, months after this index state, so the
# newest `hashable` in the snapshot bounds itself to `ghc-bignum < 1.1` and no plan exists.
# GHC 8.10.7 predates `ghc-bignum` entirely — it still uses `integer-gmp` — so the conflict
# cannot arise, and 8.10 is a line this tree lists in `tested-with`.
#
# ghcup rather than the matching `haskell` image for two reasons, both learned the hard
# way:
#
#  - the era-matching `haskell` images are built on Debian buster, which is archived, so
#    any `apt-get update` in them 404s;
#  - the cabal-install they ship cannot bootstrap Hackage's secure repository any more
#    ("root.json does not have enough signatures signed with the appropriate keys"), so
#    `cabal update` fails before a single dependency is resolved.
#
# A current cabal driving an old GHC has neither problem, and `--index-state` is what makes
# the result period-correct anyway.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/agda/agda.git /src \
 && git -C /src checkout --quiet c9c20bf3683f \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM debian:bullseye
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# Exactly the distro packages ghcup asks for, plus git (the runner needs it in-container),
# zlib and xz. The runtime halves matter as much as the -dev ones: the GHC bindist is
# built for Debian 10 and its `gmake install` step runs the freshly unpacked `ghc-pkg`,
# which links against libncurses5 and libffi7 — neither of which bullseye installs on its
# own, and without them the install step dies with a bare "gmake failed". That bindist is
# also built with libnuma support, so every link GHC then performs wants -lnuma and needs
# libnuma-dev for the linker symlink, not just the libnuma1 runtime.
ENV DEBIAN_FRONTEND=noninteractive
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        build-essential curl ca-certificates git \
        libffi-dev libffi7 libgmp-dev libgmp10 \
        libncurses-dev libncurses5 libtinfo5 libnuma1 libnuma-dev \
        zlib1g-dev pkg-config xz-utils; \
    rm -rf /var/lib/apt/lists/*

ENV BOOTSTRAP_HASKELL_NONINTERACTIVE=1 \
    BOOTSTRAP_HASKELL_GHC_VERSION=8.10.7 \
    BOOTSTRAP_HASKELL_INSTALL_NO_STACK=1 \
    BOOTSTRAP_HASKELL_ADJUST_BASHRC=0 \
    GHCUP_INSTALL_BASE_PREFIX=/opt
RUN curl --proto '=https' --tlsv1.2 -sSf https://get-ghcup.haskell.org | sh
ENV PATH=/opt/.ghcup/bin:/root/.cabal/bin:/usr/local/bin:$PATH
RUN ghc --version && cabal --version

# The Hackage snapshot the whole build resolves against — just after the anchor commit.
ENV SWESWEEP_CABAL_INDEX_STATE=2021-08-20T00:00:00Z

# alex and happy generate Agda's lexer and parser. This tree declares them in the legacy
# `build-tools` field, which cabal resolves off PATH rather than building itself.
RUN set -eux; \
    cabal update; \
    cabal install --index-state="$SWESWEEP_CABAL_INDEX_STATE" \
        --install-method=copy --installdir=/usr/local/bin \
        alex happy

# Agda source tree at the anchor commit, exported from the local clone into the build
# context (see the header).
COPY --from=swesweep-src /src /agda
WORKDIR /agda

# Make the exported tree a git repo (the export carries no .git), commit the source and tag
# it `baseline`.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "agda maxbug source" && git tag baseline

# Where `agda` looks for its primitive library, the MAlonzo/JS runtimes and agda.sty.
ENV Agda_datadir=/agda/src/data

# Agda's golden files are UTF-8 and its test driver reads them with the locale's encoding.
# Under the default C locale it dies on the first one with
# `hGetContents: invalid argument (invalid byte sequence)` — and, worse, it dies *while
# enumerating* the corpus, so the driver reports "All 0 tests passed" rather than an error
# and every subtask silently looks unmeasurable.
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8

# One script for both the image build and the per-subtask rebuild, so the flags cannot
# drift apart — `cabal list-bin` only finds the binaries if it is given the same flags as
# `cabal build`. `-fdebug` is the configuration Agda's own Makefile installs; without it
# the driver auto-skips every test that asserts on debug output.
RUN set -eux; \
    printf '%s\n' \
      '#!/bin/sh' \
      'set -eu' \
      'cd /agda' \
      'JOBS="${SWESWEEP_BUILD_JOBS:-4}"' \
      'FLAGS="-O0 -fdebug --enable-tests --index-state=$SWESWEEP_CABAL_INDEX_STATE"' \
      '# shellcheck disable=SC2086' \
      'cabal build $FLAGS --ghc-options=-j"$JOBS" exe:agda test:agda-tests' \
      '# shellcheck disable=SC2086' \
      'cp -f "$(cabal list-bin $FLAGS exe:agda)" /usr/local/bin/agda' \
      '# shellcheck disable=SC2086' \
      'cp -f "$(cabal list-bin $FLAGS test:agda-tests)" /usr/local/bin/agda-tests' \
      > /usr/local/bin/agda-build; \
    chmod +x /usr/local/bin/agda-build

RUN agda-build

CMD ["agda", "--version"]
