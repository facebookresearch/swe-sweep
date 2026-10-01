# Maximally-buggy clippy — frozen at anchor version rust-1.88.0.
#
# Built upstream by `pandora construct build-image -t clippy@rust-1.88.0`, which prepares the build
# context from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the clippy source tree at
# rust-1.88.0 into ./clippy and copies this file in as ./Dockerfile. The image holds the
# clippy git tree with a `baseline` commit+tag; the host-controlled evaluator
# (tasks/clippy/task.yaml) does `git reset --hard baseline`, then applies the per-bug
# test/gold patches.
#
# Why rust-1.88.0: clippy's apply rate climbs steeply with time (34% at rust-1.76.0, 61%
# here) while its live population barely falls, so this tag keeps nearly everything and
# doubles what applies — 133 gradeable before rebase, the largest of the batch. See
# docs/ai/040-experiments/clippy/260818-anchor-choice.md.
#
# **The toolchain is the hard pin here.** clippy is a rustc driver: it links against the
# compiler's own internal crates, so it builds only against the exact nightly its
# rust-toolchain.toml names — nightly-2025-05-01 at this tag — with rustc-dev and llvm-tools.
# A newer nightly does not merely warn, it fails to compile.
#
# `cargo test` builds as it runs, so there is no separate build step: the runner passes
# needs_build=False and the suite (ClippyUiSuite) compiles the harness on its first
# invocation. That first build is expensive, so it is warmed here at image-build time.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/rust-lang/rust-clippy.git /src \
 && git -C /src checkout --quiet rust-1.88.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM rust:1.88-bookworm
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# git supports host-directed reset/apply; the C toolchain and Python support repository tooling.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends git ca-certificates build-essential cmake python3; \
    ln -sf /usr/bin/python3 /usr/local/bin/python; \
    rm -rf /var/lib/apt/lists/*

COPY --from=swesweep-src /src /clippy
WORKDIR /clippy

# rustup honours the exported rust-toolchain.toml — `rustup show` installs exactly the
# toolchain it names (nightly-2025-05-01) with exactly the components it lists, which is
# what keeps this period-correct. Naming them on the command line instead would need one
# `--component` flag each, and would duplicate a list that already lives in the repo.
RUN rustup show

# Warm the build cache so the first census invocation is not also a cold compile of clippy
# and the ui_test harness. `TESTNAME` matches nothing, so ui_test exits as soon as it has
# built — the artifacts are what we are after, not the run.
RUN TESTNAME=__warm_cache_no_such_case__ cargo test -q --test compile-test || true

RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "clippy maxbug source" && git tag baseline

CMD ["cargo", "--version"]
