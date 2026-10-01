# Maximally-buggy oxc — frozen at anchor tag crates_v0.93.0 (2025-09-28).
#
# Built upstream by `pandora construct build-image -t oxc@crates_v0.93.0`, which prepares the build
# context from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the oxc source tree at that tag
# into ./oxc and copies this file in as ./Dockerfile. The image holds the tree with a
# `baseline` commit+tag; the host-controlled evaluator (tasks/oxc/task.yaml) does
# `git reset --hard baseline`, then applies the per-bug test/gold patches.
#
# **The toolchain is pinned by the tree**, exactly: `rust-toolchain.toml` says
# `channel = "1.90.0"`, so the base image is that Rust and `rustup show` installs precisely
# what the file asks for rather than resolving a moving channel.
#
# **Debug, not release**, the same trade-off ruff makes and for the same reason: the graded
# test is a linter rule run over a few dozen inline source snippets, so compile time
# dominates and runtime does not. oxc's own workspace already sets `debug = false` on the
# dev and test profiles, so the debug build here is not carrying debug info either.
#
# INSTA_UPDATE=no is what makes the snapshots an oracle rather than a record. `insta`
# defaults to writing a `.snap.new` beside a mismatch; with `no` it only reports, so a rule
# whose diagnostics have drifted fails instead of quietly recording the drift.
#
# The conformance corpora under the repo's own `tasks/` (test262, babel, TypeScript) are
# git submodules and are deliberately NOT fetched: they are driven by a separate
# `oxc_coverage` binary rather than by cargo test, so no subtask this image grades needs
# them. Those patches report "no targets" — see the runner's suite notes.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/oxc-project/oxc.git /src \
 && git -C /src checkout --quiet crates_v0.93.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM rust:1.90-bookworm
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends git ca-certificates build-essential; \
    rm -rf /var/lib/apt/lists/*

COPY --from=swesweep-src /src /repo
WORKDIR /repo

RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "oxc maxbug source" && git tag baseline

# rustup honours the exported rust-toolchain.toml.
RUN rustup show

ENV INSTA_UPDATE=no
ENV CARGO_TERM_COLOR=never
# `crates/oxc_traverse/build.rs` shells out to `node ./scripts/build.mjs` to regenerate the
# traverse code from the AST types — unless CI is set, in which case it returns immediately
# and the build uses the generated files checked into the tree. Its own comment says that is
# the point: "run tests etc on what's actually in repo, rather than regenerating them",
# which is exactly what a frozen benchmark image wants. So this is the intended switch, not
# a way to dodge installing Node — regenerating would let a toolchain drift the graded tree.
# It is an ENV rather than a build arg so the runner's rebuilds after a patch see it too.
ENV CI=true

# Warm the test profile: link every test binary, run none of them, so a subtask's rebuild
# after its patch is incremental.
#
# Everything that links `napi` is excluded, because a Node addon cannot be linked as an
# ordinary binary: the `napi_*` symbols come from the Node runtime that dlopens it, so the
# link fails on `undefined symbol: napi_create_array_with_length`. That is the four
# `napi/*` crates and also `oxlint`, whose `napi` feature is optional but **on by default**.
# Nothing graded is lost: the suite runs `oxc_linter`'s lib tests, and the resolver puts
# 954 of 2533 test patches on `rules::<category>::<rule>::` filters inside that crate.
RUN cargo test --workspace --no-run \
        --exclude oxc_minify_napi \
        --exclude oxc_parser_napi \
        --exclude oxc_playground_napi \
        --exclude oxc_transform_napi \
        --exclude oxlint

# Fail the build rather than the census if the pristine tree cannot pass its own suite: one
# untouched rule, run the way the runner runs it. A pristine failure reads as
# `fails_pre_gold` for every subtask and silently inflates the reproduction count.
RUN cargo test -p oxc_linter --lib -- rules::eslint::default_case::

CMD ["cargo", "--version"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
