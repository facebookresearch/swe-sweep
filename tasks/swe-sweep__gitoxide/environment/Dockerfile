# Maximally-buggy gitoxide — frozen at candidate anchor version v0.54.0.
#
# Built upstream by `pandora construct build-image -t gitoxide@v0.54.0`, which prepares the build
# context from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the source tree at v0.54.0 into
# ./gitoxide and copies this file in as ./Dockerfile. The image holds the tree with a
# `baseline` commit+tag; the host-controlled evaluator
# (tasks/gitoxide/task.yaml) does `git reset --hard baseline`, then applies the
# per-bug test/gold patches.
#
# Why v0.54.0: the SZZ coverage curve peaks there — 53 live subtasks, against 49 at the
# next-best release tag (v0.48.0). gitoxide tags every crate on every release train, so
# only the `v<x.y.z>` tags (the `gitoxide` binary crate) are meaningful anchors; the
# per-crate tags all share a date and would not distinguish anything.
#
# Why Rust 1.97.1: `Cargo.toml` declares `edition = "2024"` and `rust-version = "1.85"`, so
# the toolchain has to be recent; the lockfile is committed, so a newer compiler still
# resolves exactly the 2026-05 dependency set.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/GitoxideLabs/gitoxide.git /src \
 && git -C /src checkout --quiet v0.54.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM docker.io/library/rust:1.97.1-slim-bookworm
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# `git` and `bash` are the product's test harness, not conveniences. `gix-testtools` builds
# each test's repository by running `tests/fixtures/*.sh` through bash and the **real git
# binary**, caching the result as an archive. Without them every fixture-backed test fails
# before any patch is applied. `cmake`/`pkg-config`/`libssl-dev` are for the `max` feature's
# HTTP transport (curl).
RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        git bash ca-certificates pkg-config libssl-dev cmake make gcc g++ \
        xz-utils python3; \
    rm -rf /var/lib/apt/lists/*

# The fixture scripts commit through the real git binary and refuse to run in a directory
# owned by another uid.
RUN git config --global user.email v@x \
    && git config --global user.name v \
    && git config --global init.defaultBranch main \
    && git config --global --add safe.directory '*'

COPY --from=swesweep-src /src /gitoxide
WORKDIR /gitoxide

# Make the exported tree a git repo (the export carries no .git), commit the source and
# tag it `baseline`. `target/` is in gitoxide's own .gitignore, so it is NOT part of the
# baseline commit and the consumers' `git reset --hard baseline && git clean -fdq` (no -x)
# leaves the warm build below alone.
RUN git init -q \
    && git add -A && git commit -q -m "gitoxide maxbug source" && git tag baseline

# Warm the build: compile every crate's test targets so a subtask's run is an incremental
# recompile of one crate rather than a cold build of a ~50-crate workspace.
RUN cargo test --workspace --no-run

# Generate the fixture archives now, while the build still has a network and a writable
# tree. `gix-testtools` runs each `tests/fixtures/*.sh` once and caches the result; doing
# it here means the census does not pay for it per subtask — and, more importantly, a
# script that needs the network would fail there and be read as a bug.
RUN cargo test -p gix-config -p gix-ref -p gix-object 2>&1 | tail -20

# A reproduction run has no network (unlike this build, which goes through FwdProxy), so
# say so: cargo must fail loudly on a dependency it does not already have, rather than hang
# until the runner's timeout and report the subtask as unmeasurable.
ENV CARGO_NET_OFFLINE=true \
    CARGO_TERM_COLOR=never \
    RUST_BACKTRACE=1

CMD ["cargo", "--version"]
