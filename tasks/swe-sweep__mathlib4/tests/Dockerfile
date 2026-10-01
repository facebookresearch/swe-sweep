# Maximally-buggy mathlib4 — one recipe for every candidate anchor.
#
# Built upstream by `pandora construct build-image -t mathlib4@<v>`, which prepares the build
# context under data/tasks/mathlib4/maxbug/<v>/context/: it exports the mathlib4 source
# tree at the candidate tag FROM THE LOCAL CLONE (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md) into ./mathlib4, and copies this file in as
# ./Dockerfile.
#
# This is the only maxbug image that has to *compile a mathematics library*, and it is
# built out of two things upstream already provides:
#
# - **elan** picks the compiler. The tree pins its own Lean in `lean-toolchain`, and elan
#   reads that file, so nothing here names a version — the same Dockerfile is correct for
#   every candidate.
# - **`lake exe cache get`** is what makes the build minutes instead of hours: mathlib's
#   CI publishes the compiled `.olean` for every commit on master, and every candidate
#   anchor is such a commit. `lake build` afterwards is a no-op that proves the cache was
#   complete.
#
# The build tree is `.lake/` INSIDE the repo, which is the one place lake will put it. That
# is safe here only because `.lake` is in mathlib4's `.gitignore` and the consumers reset
# with `git clean -fdq` and no `-x`, so the compiled library survives a subtask reset. A
# `-x` would delete several gigabytes of `.olean` and turn every subtask into a full build.
#
# Built at Meta through FwdProxy like every other maxbug image: `pandora construct
# build-image` wraps the build in `sudo with-proxy` and passes `--network=host` (rootless
# podman can't route to FwdProxy's IPv6 — see
# docs/ai/030-debug/260626-maxbug-image-registry-blocked.md). With FwdProxy in front of
# apt, apt's unprivileged `_apt` sandbox user cannot read the proxied download, so apt is
# told to run as root before it touches the network.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/leanprover-community/mathlib4.git /src \
 && git -C /src checkout --quiet v4.24.0-rc1 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM debian:trixie-slim
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        git curl ca-certificates unzip gcc libc6-dev; \
    rm -rf /var/lib/apt/lists/*
# gcc and libc6-dev are not optional: Lean shells out to a C compiler to link the
# executables lake builds (`cache`, the test drivers), even though mathlib itself is pure
# Lean.

# elan, the Lean toolchain manager, installed for every user rather than into a home
# directory — the runner does not control which user the container runs as.
ENV ELAN_HOME=/usr/local/elan \
    PATH=/usr/local/elan/bin:$PATH
RUN curl -fsSL https://elan.lean-lang.org/elan-init.sh \
        | sh -s -- -y --no-modify-path --default-toolchain none

# mathlib4 source tree at the candidate ref, exported from the local clone into the build
# context (see the header).
COPY --from=swesweep-src /src /mathlib4
WORKDIR /mathlib4

# Make the exported tree a git repo (the export carries no .git), commit the source and
# tag it `baseline` — a SOURCE-ONLY tree, so an agent's extracted patch can never carry a
# build artifact.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git remote add origin https://github.com/leanprover-community/mathlib4.git \
    && git add -A && git commit -q -m "mathlib4 maxbug source" && git tag baseline
# The `origin` remote is metadata only — nothing fetches from it — but `lake exe cache
# get` reads it to work out which repository's cache bucket to ask for, and dies with
# "No such remote 'origin'" without it. The export carries no remotes.

# Install exactly the Lean the tree pins, then pull the published build and confirm it is
# complete. `lake exe cache get` builds the little `cache` executable first, which is why
# this is one step and not two.
RUN elan toolchain install "$(cat lean-toolchain)" \
    && elan override set "$(cat lean-toolchain)" \
    && lake exe cache get \
    && lake build

CMD ["lake", "env", "lean", "--version"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
