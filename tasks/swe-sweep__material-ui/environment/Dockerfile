# Maximally-buggy material-ui — frozen at anchor version v5.6.1.
#
# Built upstream by `pandora construct build-image -t material-ui@v5.6.1`, which prepares the build
# context from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the source tree at v5.6.1 into
# ./material-ui and copies this file in as ./Dockerfile. The image holds the tree with a
# `baseline` commit+tag; the host-controlled evaluator (tasks/material-ui/task.yaml) does
# `git reset --hard baseline`, then applies the per-bug test/gold patches.
#
# Why v5.6.1: both patches apply for 54 subtasks here, against 36 at v6.0.0, 33 at v5.11.0,
# 24 at v6.4.0, 21 at v5.15.0 and 11 at v4.12.4. It is also where the coverage curve peaks
# (96 live) — the two measures agree here, which they did not for ant-design. The v4 side
# loses badly because the v4 -> v5 move renamed every `@material-ui/*` package to `@mui/*`.
# See docs/ai/040-experiments/material-ui/260820-anchor-choice.md.
#
# Why Node 16: v5.6.1 is April 2022 and its CI ran Node 14/16; the yarn-1 workspaces install
# and mocha 9 both predate the Node 18 resolver changes.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/mui/material-ui.git /src \
 && git -C /src checkout --quiet v5.6.1 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM node:16-bullseye
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# Built at Meta through FwdProxy: `pandora construct build-image` wraps the build in
# `sudo with-proxy` with `--network=host`, and apt's unprivileged `_apt` sandbox user cannot
# read a proxied download — so apt is told to run as root before it touches the network (see
# docs/ai/030-debug/260626-maxbug-image-registry-blocked.md).
#
# git supports host-directed reset/apply. Python remains available for package build tools.
RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    apt-get update; \
    apt-get install -y --no-install-recommends git ca-certificates python3; \
    ln -sf /usr/bin/python3 /usr/local/bin/python; \
    rm -rf /var/lib/apt/lists/*

# Host-driven evaluation supplies complete commands, so do not let the base image prepend `node`.
ENTRYPOINT []

COPY --from=swesweep-src /src /material-ui
WORKDIR /material-ui

# `--frozen-lockfile` is what makes the install period-correct: the committed yarn.lock
# decides every version, not today's registry. `--network-timeout` because this install pulls
# a large tree through the proxy and yarn's default 30s gives up on the slowest tarballs.
RUN yarn install --frozen-lockfile --network-timeout 600000

# mui's babel.config.js selects its test-only transforms from NODE_ENV, and its mocha setup
# reads it too; without it every spec fails to parse. It belongs in the image because it is a
# property of this environment rather than of any subtask.
ENV NODE_ENV=test

# Prove the suite is green *before* any patch is applied. A pristine failure reads as
# `fails_pre_gold` for every subtask and would quietly inflate the whole census; catching it
# at image-build time is the cheapest place. One small, stable package suite is enough.
RUN npx --no-install mocha 'packages/mui-utils/src/**/*.test.{js,ts,tsx}' --exit --timeout 60000

RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "material-ui maxbug source" && git tag baseline

CMD ["node", "-e", "console.log('material-ui', require('/material-ui/package.json').version)"]
