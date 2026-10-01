# Maximally-buggy ruff — frozen at anchor version 0.8.1 (2024-11-29).
#
# Built upstream by `pandora construct build-image -t ruff@0.8.1`, which prepares the build context
# from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the ruff source tree at 0.8.1
# into ./ruff and copies this file in as ./Dockerfile. The image holds the tree with a
# `baseline` commit+tag; the host-controlled evaluator (tasks/ruff/task.yaml)
# does `git reset --hard baseline`, then applies the per-bug test/gold patches.
#
# **The toolchain is pinned by the tree.** ruff commits a `rust-toolchain.toml` naming an
# exact channel (1.82 at this tag) and uses edition features close to it, so the base
# image is that Rust and `rustup show` installs exactly what the file asks for. A newer
# toolchain is not merely a warning here.
#
# The suite is `cargo test`, which builds as it runs, so there is no separate build step:
# the runner passes needs_build=False. **Debug, not release** — the census pays for a
# rebuild of `ruff_linter` twice per subtask (pre-gold and post-gold) and that crate is
# large, so compile time dominates; the fixtures a rule lints are a few hundred lines, and
# a debug binary lints them in milliseconds either way.
#
# `cargo test --no-run` warms exactly that: every test binary linked, nothing executed.
#
# INSTA_UPDATE=no is what makes the snapshots an oracle rather than a record. `insta`
# defaults to writing a `.snap.new` beside a mismatch; with `no` it only reports, so a
# rule whose diagnostics have drifted fails instead of quietly recording the drift.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/astral-sh/ruff.git /src \
 && git -C /src checkout --quiet 0.8.1 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM rust:1.82-bookworm
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends git ca-certificates build-essential python3; \
    ln -sf /usr/bin/python3 /usr/local/bin/python; \
    rm -rf /var/lib/apt/lists/*

COPY --from=swesweep-src /src /ruff
WORKDIR /ruff

RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "ruff maxbug source" && git tag baseline

# rustup honours the exported rust-toolchain.toml.
RUN rustup show

ENV INSTA_UPDATE=no
ENV CARGO_TERM_COLOR=never

# Warm the test profile: link every test binary, run none of them.
RUN cargo test --workspace --no-run

CMD ["cargo", "--version"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
