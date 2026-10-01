# Maximally-buggy datafusion — frozen at candidate anchor version 52.0.0.
#
# Built upstream by `pandora construct build-image -t datafusion@52.0.0`, which prepares the build
# context under data/datafusion/maxbug/52.0.0/context/: it exports the datafusion source
# tree at tag 52.0.0 FROM THE LOCAL CLONE (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md) into ./datafusion, and copies this file in
# as ./Dockerfile.
#
# Why 52.0.0: datafusion's bug-coverage curve peaks in January 2026 at 173 live subtasks,
# and 52.0.0 is the release tag sitting on that peak, also with 173. Unusually for this
# benchmark the peak is the *newest* end of the history — datafusion is a young, fast
# project whose bug population is still growing — so nothing is traded away by taking it.
#
# The toolchain is pinned rather than the dependencies: datafusion commits a Cargo.lock,
# but its MSRV floor moves and a 2026 tree wants a recent rustc.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/apache/datafusion.git /src \
 && git -C /src checkout --quiet 52.0.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

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
        git ca-certificates python3 python-is-python3 \
        pkg-config libssl-dev protobuf-compiler libprotobuf-dev; \
    rm -rf /var/lib/apt/lists/*
# libprotobuf-dev, not just the compiler: the `substrait` crate's build script compiles
# .proto files that import `google/protobuf/any.proto`, and those well-known types ship in
# the -dev package's include tree. Without it the whole workspace fails to build.
# The Python alias is retained only for repository-owned tooling; benchmark control runs on the host.

# NOT `/datafusion`: the sqllogictest harness normalizes the workspace root out of the
# query plans it compares, by replacing that path string with `WORKSPACE_ROOT`. If the
# root is `/datafusion`, the *inner* `datafusion/` directory matches the same string and
# every plan comes out as `WORKSPACE_ROOT/WORKSPACE_ROOT/core/...`, so every `explain`
# case in every `.slt` file fails — at the pristine baseline, for no reason to do with
# any bug.
COPY --from=swesweep-src /src /repo
WORKDIR /repo

# datafusion keeps its test *data* in three git submodules, and `git archive` does not
# export a submodule's contents — it leaves nothing at all. Without them the `.slt` suite
# still runs, but every table is empty, so a query that should return `0 0 0 0 0` returns
# `NULL NULL NULL NULL NULL` and the file fails at the pristine baseline. That is the
# worst kind of failure for this stage: it makes `fails_pre_gold` true for reasons that
# have nothing to do with the bug.
#
# Cloned at the exact commits the anchor pins (`git ls-tree 52.0.0`), and stripped of
# their own history afterwards so the baseline commit below is a plain source tree.
#
# Skipped for a submodule the build context already carries: once the submodule clones
# exist locally, `prepare_build_context` exports each one at its pinned sha into the
# exported tree, and cloning on top of a populated directory is a hard `git` error. The
# two paths write the same commit, so whichever ran first wins.
RUN set -eux; \
    for spec in \
        "testing https://github.com/apache/arrow-testing 0d60ccae40d0e8f2d22c15fafb01c5d4be8c63a6" \
        "parquet-testing https://github.com/apache/parquet-testing 107b36603e051aee26bd93e04b871034f6c756c0" \
        "datafusion-testing https://github.com/apache/datafusion-testing eccb0e4a426344ef3faf534cd60e02e9c3afd3ac" \
    ; do \
        set -- $spec; \
        if [ -n "$(ls -A "/repo/$1" 2>/dev/null)" ]; then continue; fi; \
        git clone -q "$2" "/repo/$1"; \
        git -C "/repo/$1" checkout -q "$3"; \
        rm -rf "/repo/$1/.git"; \
    done

# Make the exported tree a git repo (the export carries no .git), commit the source and
# tag it `baseline`. The submodule data above is committed with it, so the
# `git reset --hard baseline && git clean -fdq` between subtasks restores it rather than
# deleting it as untracked. `target/` is gitignored and so is left alone by that reset
# (no -x), which is what keeps the warm build below.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "datafusion maxbug source" && git tag baseline

# Warm the build. Both halves of datafusion's regression coverage have to be compiled
# here, because a reproduction run has no network:
#   - the per-crate Rust integration tests (`<crate>/tests/*.rs`), of which the core
#     crate's are by far the largest set;
#   - the `sqllogictests` harness, which is how the `.slt` files under
#     `datafusion/sqllogictest/test_files/` are run — over half of all datafusion test
#     patches touch only those.
RUN cargo test --no-run -p datafusion --tests \
    && cargo test --no-run -p datafusion-sqllogictest --test sqllogictests

# Say the run is offline, so cargo fails loudly on a dependency this image does not
# already have rather than hanging until the runner's timeout.
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
