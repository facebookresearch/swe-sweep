# Maximally-buggy tokio — frozen at candidate anchor version tokio-1.33.0.
#
# Built upstream by `pandora construct build-image -t tokio@1.33.0`, which prepares the build
# context under data/tokio/maxbug/1.33.0/context/: it exports the tokio source tree at
# tokio-1.33.0 FROM THE LOCAL CLONE (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md) into ./tokio, and copies this file in as
# ./Dockerfile.
#
# Why 1.33.0: tokio's bug-coverage curve is remarkably flat — it sits between 35 and 40
# live subtasks for a whole year after the 2020-11 peak of 40, and is still at 35 in late
# 2023. tokio-1.33.0 (2023-10) is the latest tag on that plateau, and being three years
# newer than the peak is worth the four subtasks: tokio commits no Cargo.lock, so cargo
# resolves the *newest* semver-compatible dependency of everything at build time, and the
# older the tree, the less likely that resolution still compiles.
#
# Why a modern toolchain rather than a period-correct one: same reason. With no lockfile,
# a 2023 rustc cannot build 2026's dependency graph (getrandom 0.4 alone needs edition
# 2024), so the *toolchain* is pinned here instead of the dependencies. Anything that
# needs the exact 2023 dependency set is a rebuild away from the pinned Cargo.lock this
# image bakes in.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/tokio-rs/tokio.git /src \
 && git -C /src checkout --quiet tokio-1.33.0 \
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

RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        git ca-certificates python3 python-is-python3; \
    rm -rf /var/lib/apt/lists/*
# The Python alias is retained only for repository-owned tooling; benchmark control runs on the host.

# tokio source tree at the candidate ref, exported from the local clone into the build
# context (see the header).
COPY --from=swesweep-src /src /tokio
WORKDIR /tokio

# Make the exported tree a git repo (the export carries no .git), commit the source and
# tag it `baseline`. Both `target/` and `Cargo.lock` are in tokio's own .gitignore, so
# they are NOT part of the baseline commit and the consumers'
# `git reset --hard baseline && git clean -fdq` (no -x) leaves them alone: every subtask
# starts from the pristine sources but keeps the warm build below.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && printf '%s\n' '' '# SWE-sweep: route every crates.io `tokio` requirement to the workspace crate; a' '# second `tokio` in the graph (via wasm-bindgen-futures 0.4.79) makes `-p tokio` ambiguous.' '[patch.crates-io]' 'tokio = { path = "tokio" }' >> Cargo.toml \
    && git add -A && git commit -q -m "tokio maxbug source" && git tag baseline

# Warm the build: resolve the whole dependency graph into Cargo.lock, download it into
# the registry cache, and compile every test target of the four published crates. This is
# what makes a per-subtask run an incremental recompile of one crate rather than a cold
# build of the workspace.
#
# `--features full` is tokio's own "all the runtime" feature; its integration tests do not
# compile without it.
RUN cargo test --no-run -p tokio --features full --tests \
    && cargo test --no-run -p tokio-util --all-features --tests \
    && cargo test --no-run -p tokio-stream --all-features --tests \
    && cargo test --no-run -p tokio-test --all-features --tests

# A reproduction run has no network (unlike this build, which goes through FwdProxy), so
# say so: cargo must fail loudly on a dependency it does not already have, rather than
# hang until the runner's timeout and report the subtask as unmeasurable.
ENV CARGO_NET_OFFLINE=true \
    CARGO_TERM_COLOR=never \
    RUST_BACKTRACE=1

CMD ["cargo", "--version"]
