# Maximally-buggy Elixir — frozen at the v1.15.7 release tag.
#
# Built upstream by `pandora construct build-image -t elixir@1.15.7`, which prepares the build
# context from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the Elixir source tree at that
# tag into ./elixir and copies this file in as ./Dockerfile. The image holds the tree with
# a `baseline` commit+tag; the host-controlled evaluator
# (tasks/elixir/task.yaml) does `git reset --hard baseline`, then applies the
# per-bug test/gold patches and rebuilds.
#
# Three things are specific to an Elixir task:
#
# 1. **The Erlang release is part of the anchor.** Elixir compiles to BEAM bytecode and
#    its own suite asserts on OTP behaviour, so the OTP major is as much a version pin as
#    the Elixir tag. OTP 26 is the newest release this tree's CI matrix tests, and the
#    one it was released against.
#
# 2. **The build is the whole distribution and it is cheap.** `make compile` builds all
#    six applications from source in a couple of minutes, and an incremental rebuild after
#    a gold patch is far less, so every subtask can afford one.
#
# 3. **epmd has to be reachable.** The standard library's suite runs as a named node
#    (upstream passes `--sname primary`), and a named node needs the Erlang port mapper.
#    `elixir --sname` starts it itself, but only if the binary is on PATH — which it is in
#    the official erlang image.
# Fully qualified: podman enforces short-name resolution and cannot prompt in a build.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/elixir-lang/elixir.git /src \
 && git -C /src checkout --quiet v1.15.7 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM docker.io/library/erlang:26
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

ENV DEBIAN_FRONTEND=noninteractive
RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    echo 'Acquire::Retries "5";' >> /etc/apt/apt.conf.d/10sandbox; \
    apt-get update; \
    apt-get install -y --no-install-recommends build-essential git ca-certificates; \
    rm -rf /var/lib/apt/lists/*

# Set before anything runs elixir: the BEAM takes its filename encoding from the locale,
# and under the default C locale it comes up latin1, which Elixir warns about on every
# single invocation and which changes how it reads UTF-8 paths and sources.
ENV LANG=C.UTF-8 LC_ALL=C.UTF-8

# Elixir source tree at the anchor tag, exported from the local clone into the build
# context (see the header).
COPY --from=swesweep-src /src /elixir
WORKDIR /elixir

# Make the exported tree a git repo (the export carries no .git), commit the source and
# tag it `baseline`.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "elixir maxbug source" && git tag baseline

# One script for both the image build and the per-subtask rebuild, so the flags cannot
# drift apart.
RUN set -eux; \
    printf '%s\n' \
      '#!/bin/sh' \
      'set -eu' \
      'cd /elixir' \
      'make compile' \
      > /usr/local/bin/elixir-build; \
    chmod +x /usr/local/bin/elixir-build

RUN elixir-build && bin/elixir --version

CMD ["/elixir/bin/elixir", "--version"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
