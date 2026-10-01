# Maximally-buggy jest — frozen at anchor v29.0.0.
#
# Built upstream by `pandora construct build-image -t jest@29.0.0`, which prepares the build context
# from the local clone (no GitHub access — see docs/ai/010-design/005-style-conventions.md):
# it exports the source tree at v29.0.0 into ./jest and copies this file in as ./Dockerfile.
# The image holds the tree with a `baseline` commit+tag; the host-controlled evaluator
# (tasks/jest/task.yaml) does `git reset --hard baseline`, then applies the per-bug
# test/gold patches.
#
# Why v29.0.0: it is the interior maximum of the patch-applies probe — 37 subtasks with both
# patches applying, against 34 at 28.1.3 and 29.4.0 on either side and 23 by 29.7.0. See
# docs/ai/040-experiments/jest/260819-anchor-choice.md.
#
# Why Node 18: v29's `engines.node` is `^14.15.0 || ^16.10.0 || >=18.0.0`, and 18 is the
# newest of those — the one whose npm registry metadata and native builds still resolve.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/jestjs/jest.git /src \
 && git -C /src checkout --quiet v29.0.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM node:18-bullseye
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

COPY --from=swesweep-src /src /jest
WORKDIR /jest

# **yarn 3, from the tree's own checked-in release.** `.yarnrc.yml` sets
# `yarnPath: .yarn/releases/yarn-3.2.3.cjs`, so invoking `yarn` runs that file rather than the
# node image's bundled yarn 1 — which is what makes the install period-correct without
# corepack having to fetch anything. `--immutable` is yarn 3's `--frozen-lockfile`.
#
# `nodeLinker: node-modules` (also in .yarnrc.yml) is why `npx --no-install jest` works in the
# runner: this tree is not PnP, so there is a real `node_modules/.bin/jest`.
#
# **yarn 3 does not read `http_proxy`.** Unlike yarn 1 — which every other JS image here uses
# and which picks the variable up — yarn 3 only honours its own `httpProxy`/`httpsProxy`
# settings, so inside the build container it resolves registry.yarnpkg.com directly and dies
# on `getaddrinfo EAI_AGAIN`. Passing them through as `YARN_*` env vars is the same setting by
# yarn's own env convention, and costs nothing on a host with direct egress (the variables are
# simply unset there).
RUN set -eux; \
    if [ -n "${http_proxy:-${HTTP_PROXY:-}}" ]; then \
        export YARN_HTTP_PROXY="${http_proxy:-$HTTP_PROXY}"; \
        export YARN_HTTPS_PROXY="${https_proxy:-${HTTPS_PROXY:-${http_proxy:-$HTTP_PROXY}}}"; \
    fi; \
    yarn install --immutable

# jest's own packages are TypeScript and its tests import each package's `build/`, not its
# `src/`. The three steps are the repo's own `yarn build`: build:js transpiles, build:ts emits
# the declarations, bundle:ts rolls up the public types.
ENV NODE_OPTIONS=--max-old-space-size=4096
RUN yarn build

RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "jest maxbug source" && git tag baseline

CMD ["node", "-e", "console.log('jest', require('/jest/package.json').version)"]
