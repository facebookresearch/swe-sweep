# Maximally-buggy swc — the 1.2.x anchors (spring 2022, where the coverage curve peaks).
#
# Built upstream by `pandora construct build-image -t swc@<v>`, which prepares the build context
# under data/tasks/swc/_local_only/maxbug/<v>/context/: it exports the source tree at the
# anchor tag FROM THE LOCAL CLONE (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md) into ./swc, exports the two pinned
# test-corpus submodules into it, and copies this file in as ./Dockerfile.
#
# One Dockerfile for the whole 1.2.x shortlist: every tag on it pins the same
# `rust-toolchain` nightly and the same committed Cargo.lock, so they all want the same
# image recipe.

# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/swc-project/swc.git /src \
 && git -C /src checkout --quiet v1.2.184 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM docker.io/library/rust:1.61.0-slim-bullseye
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    sed -i '\|^deb http://security.debian.org|d' /etc/apt/sources.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        git ca-certificates curl xz-utils pkg-config libssl-dev cmake clang libclang-dev \
        build-essential python3 python-is-python3; \
    rm -rf /var/lib/apt/lists/*
# The Python alias is retained only for repository-owned tooling; benchmark control runs on the host.

# Node, because part of swc's suite *runs* the code it compiles. `crates/swc/tests/exec.rs`
# shells out to `node` and diffs the output, and without it all sixteen of its cases fail in
# the pristine tree — which reads as `fails_pre_gold` for every subtask that lands there and
# makes the target unusable, since `passes_post_gold` requires the whole target green.
# Debian bullseye's own nodejs is 12, far below what this era's fixtures expect, so the
# official 18.x tarball is unpacked instead.
ENV NODE_VERSION=18.20.4
RUN set -eux; \
    curl -fsSL -o /tmp/node.tar.xz \
      "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz"; \
    tar -xJf /tmp/node.tar.xz -C /usr/local --strip-components=1 \
      --exclude CHANGELOG.md --exclude LICENSE --exclude README.md; \
    rm /tmp/node.tar.xz; \
    node --version

# swc source tree at the candidate ref, exported from the local clone into the build
# context (see the header). The two test-corpus submodules — tc39's test262 parser corpus
# and html5lib's tokenizer/tree-construction corpus — are exported into it at their pinned
# commits; `git archive` writes a submodule as an empty directory, which would turn every
# conformance case into a silent skip rather than a failure.
COPY --from=swesweep-src /src /swc
WORKDIR /swc

# The tree's own `rust-toolchain` pins a nightly, and `.cargo/config.toml` passes `-Z
# new-llvm-pass-manager=no` in `build.rustflags` — an unstable flag, so stable cargo
# refuses to build this tree at all. Install the pinned nightly here rather than let the
# first subtask discover it: a reproduction run is offline and rustup could not fetch it.
RUN rustup toolchain install "$(tr -d '[:space:]' < rust-toolchain)" --profile minimal --component rustfmt

# Debug info OFF before anything is compiled. swc's test surface is ~90 crates of heavily
# monomorphised generics; with the default `debug = 2` for the test profile the `target/`
# dir runs to tens of GB, which is an image no Batch node wants to pull. It has to be set
# before the warm build below, not after — the artifacts are already on disk by then.
ENV CARGO_PROFILE_TEST_DEBUG=0 \
    CARGO_PROFILE_DEV_DEBUG=0 \
    CARGO_PROFILE_TEST_INCREMENTAL=false \
    CARGO_PROFILE_DEV_INCREMENTAL=false

# Make the exported tree a git repo (the export carries no .git), commit the sources and
# tag them `baseline` — a SOURCE-ONLY tag. `target/` is in swc's own .gitignore, so it is
# not part of the baseline commit and the runner's `git reset --hard baseline && git clean
# -fdq` (no -x) resets the sources between subtasks while keeping the warm build below.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "swc maxbug source" && git tag baseline

# Warm the build: compile every test target of the workspace, so a per-subtask run is an
# incremental recompile plus a relink rather than a cold build of the whole graph.
#
# The exclusions are the crates that are not host-testable rather than crates we choose to
# skip: the two `binding_*` node addons link against a Node ABI that is not in the image,
# `binding_core_wasm` is a cdylib for wasm32, and `swc_plugin*` builds a wasmer runtime for
# a plugin ABI no crawled subtask touches. Subtasks whose diff lands only in those report
# "no targets" instead of failing.
RUN cargo test --no-run --workspace \
      --exclude binding_core_node \
      --exclude binding_core_wasm \
      --exclude binding_css_node \
      --exclude swc_plugin \
      --exclude swc_plugin_macro \
      --exclude swc_plugin_runner \
      --exclude swc_plugin_testing \
      --exclude swc_plugin_proxy

# A reproduction run has no network (unlike this build, which goes through FwdProxy), so
# say so: cargo must fail loudly on a dependency it does not already have, rather than
# hang until the runner's timeout and report the subtask as unmeasurable.
ENV CARGO_NET_OFFLINE=true \
    CARGO_TERM_COLOR=never \
    RUST_BACKTRACE=1

CMD ["cargo", "--version"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
