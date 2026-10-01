# Maximally-buggy react-router — frozen at anchor 7.7.1 (tag `react-router@7.7.1`).
#
# Built upstream by `pandora construct build-image -t react-router@7.7.1`, which prepares the build
# context from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the source tree at that tag into
# ./react-router and copies this file in as ./Dockerfile. The image holds the tree with a
# `baseline` commit+tag; the host-controlled evaluator (tasks/react-router/task.yaml)
# does `git reset --hard baseline`, then applies the per-bug test/gold patches.
#
# Why 7.7.1: the repo has two structural breaks — 6.4 introduced the data routers and 7.0
# absorbed Remix, renaming every package and re-tagging per package. 7.7.1 is the interior
# maximum of the probe across both: 21 subtasks with both patches applying, against 15 at
# 7.0.0, 10 at 8.0.0 and 4 anywhere in 6.x. See
# docs/ai/040-experiments/react-router/260819-anchor-choice.md.
#
# Why Node 20: the tree's `engines.node` is `>=20.0.0`.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/remix-run/react-router.git /src \
 && git -C /src checkout --quiet react-router@7.7.1 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM node:20-bookworm
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# git supports host-directed reset/apply. Python remains available for package build tools.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends git ca-certificates python3; \
    ln -sf /usr/bin/python3 /usr/local/bin/python; \
    rm -rf /var/lib/apt/lists/*

# Host-driven evaluation supplies complete commands, so do not let the base image prepend `node`.
ENTRYPOINT []

COPY --from=swesweep-src /src /react-router
WORKDIR /react-router

# pnpm, pinned by the tree's own `packageManager` field and installed by corepack — so the
# version is the repo's, not today's. `--frozen-lockfile` makes the install period-correct.
RUN corepack enable && corepack prepare --activate \
    && pnpm install --frozen-lockfile

# CI builds before it tests, so the image does too. Note this is *not* what makes a gold patch
# visible: the shared jest config maps `react-router` and every `@react-router/*` to the
# package's `index.ts`, so the suite transforms the TypeScript sources directly and a fix is
# live the moment it is applied. The build is here for the few paths that resolve to `dist/`.
ENV NODE_OPTIONS=--max-old-space-size=4096
RUN pnpm build

RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "react-router maxbug source" && git tag baseline

CMD ["node", "-e", "console.log('react-router', require('/react-router/packages/react-router/package.json').version)"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
