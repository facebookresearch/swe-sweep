# Maximally-buggy syn — frozen at anchor version 1.0.36.
#
# Built upstream by `pandora construct build-image -t syn@1.0.36`, which prepares the build context
# from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the source tree at 1.0.36 into
# ./syn and copies this file in as ./Dockerfile. The image holds the tree with a `baseline`
# commit+tag; the host-controlled evaluator (tasks/syn/task.yaml) does
# `git reset --hard baseline`, then applies the per-bug test/gold patches.
#
# Why 1.0.36: syn's bug population is historical. The coverage curve is flat at 12-14 live
# subtasks across the whole 1.0 line (2020-05 to 2021-04) and peaks at 14 on 1.0.35/1.0.36;
# by the 2.0 line it is down to 2-3 and by 3.0 it is zero. See
# docs/ai/040-experiments/syn/260824-seed-funnel.md.
#
# Why a modern toolchain and not a period-correct one. syn commits no Cargo.lock, so cargo
# resolves the *newest* semver-compatible release of everything at build time. Only the
# direct dev-dependencies are held back by their minor-version requirements (`reqwest =
# "0.10"`, `insta = "0.16"`); everything reached transitively — `idna`, `icu_*`, `libc`,
# `rustix` — resolves to a 2026 release. Those are edition-2024 crates, so an older cargo
# refuses to parse their manifests before it compiles a single line, and a period-correct
# 1.45 is hopeless. The toolchain is therefore pinned forward and `--cap-lints warn` (below)
# is what carries the 2020 half of the graph.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/dtolnay/syn.git /src \
 && git -C /src checkout --quiet 1.0.36 \
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

# git supports host-directed reset/apply. pkg-config + libssl-dev are what the 2020
# `reqwest 0.10` dev-dependency links against (it defaults to native-tls); without them
# every test target fails to link, not just the two that use the network.
RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        git ca-certificates pkg-config libssl-dev; \
    rm -rf /var/lib/apt/lists/*

COPY --from=swesweep-src /src /syn
WORKDIR /syn

# Make the exported tree a git repo (the export carries no .git), commit the source and tag
# it `baseline`. `target/` and `Cargo.lock` are in syn's own .gitignore, so they are NOT
# part of the baseline commit and the consumers' `git reset --hard baseline &&
# git clean -fdq` (no -x) leaves them alone: every subtask starts from pristine sources but
# keeps the warm build below.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "syn maxbug source" && git tag baseline

# `--cap-lints warn` is what makes a 2020 crate graph compile under a 2026 rustc: several
# lints that were warnings in 2020 are denied now. It is set before the warm build and kept
# in the final ENV below, because the census recompiles on every subtask and must see the
# same flags.
ENV RUSTFLAGS="--cap-lints warn"

# Warm the build: resolve the whole dependency graph into Cargo.lock, download it into the
# registry cache, and compile every test target. This is what makes a per-subtask run an
# incremental recompile rather than a cold build.
#
# `--all-features` is what syn's own CI runs: `full`, `extra-traits`, `visit`, `fold` and
# friends are off by default, and most of the syntax-tree code a bug lives in is behind
# `full`. Without it the majority of the corpus does not even compile.
RUN cargo test --no-run --all-features --tests
RUN cargo build --benches --all-features 2>/dev/null || true

# Prove the suite is green *before* any patch is applied. A pristine failure reads as
# `fails_pre_gold` for every subtask and would quietly inflate the whole census.
#
# `test_expr` and `test_item` are the two largest hand-written round-trip suites and are
# where most of the graded test patches land. The two corpus suites — `test_round_trip` and
# `test_precedence` — are deliberately not run here and are excluded by the runner: they
# fetch crates from crates.io through `tests/repo/`, and a reproduction container has no
# network.
#
# `test_macro_variable_match_arm` is the one case this tree cannot pass against a current
# proc-macro2: it builds a `Punct` out of `'_'`, which proc-macro2 accepted in 2020 and now
# rejects with "unsupported proc macro punctuation character". Pinning proc-macro2 back is
# not an option — the 2020 dev-dependency graph drags in modern derive crates that require a
# recent one — so the case is skipped here and named, rather than left to look like a green
# suite. It cannot reach the census: the runner selects cases by the names scraped from the
# test patch (`--exact`), so a subtask's pre/post-gold run never includes it.
RUN cargo test --all-features --test test_expr --test test_item -- --skip test_macro_variable_match_arm

# A reproduction run has no network (unlike this build, which goes through FwdProxy), so say
# so: cargo must fail loudly on a dependency it does not already have, rather than hang
# until the runner's timeout and report the subtask as unmeasurable.
ENV RUSTFLAGS="--cap-lints warn" \
    CARGO_NET_OFFLINE=true \
    CARGO_TERM_COLOR=never \
    RUST_BACKTRACE=1

CMD ["cargo", "--version"]
