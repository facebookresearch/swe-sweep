# Maximally-buggy nuxt — frozen at anchor version 4.3.0.
#
# Built upstream by `pandora construct build-image -t nuxt@4.3.0`, which prepares the build context
# from the local clone (no GitHub access — see docs/ai/010-design/005-style-conventions.md):
# it exports the nuxt source tree at v4.3.0 into ./nuxt and copies this file in as
# ./Dockerfile. The image holds the nuxt git tree with a `baseline` commit+tag; the
# host-controlled evaluator (tasks/nuxt/task.yaml) does `git reset --hard baseline`, then
# applies the per-bug test/gold patches.
#
# nuxt is TYPESCRIPT run through vitest's own transform, so there is nothing to compile after
# a patch and the runner passes needs_build=False. What the image *does* prepare once, at
# build time, is the two things vitest cannot do per-subtask without paying for them every
# run: the pnpm install, and `test:prepare`, which generates the test fixtures' .nuxt dirs.
# Both are part of the baseline; a gold patch never invalidates them, because it only ever
# touches packages/*/src.
#
# Why 4.3.0: nuxt is the case where the coverage peak also wins — 101 subtasks live and 48
# still applying, the best of the five candidates. See
# docs/ai/040-experiments/nuxt/260818-anchor-choice.md.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/nuxt/nuxt.git /src \
 && git -C /src checkout --quiet v4.3.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM node:22-bookworm
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

COPY --from=swesweep-src /src /nuxt
WORKDIR /nuxt

# pnpm at the version the repo pins in `packageManager`, via corepack — resolving it any
# other way would install a different lockfile interpretation than upstream's CI uses.
RUN corepack enable && corepack prepare --activate

# The workspace at this tag. `--frozen-lockfile` is what makes the install period-correct:
# the committed pnpm-lock.yaml decides every version, not today's registry.
RUN pnpm install --frozen-lockfile

# `build` prepacks each package (the unit tests import from src, but the fixtures resolve the
# built entry points) and `test:prepare` generates the fixture .nuxt dirs the suite needs.
RUN pnpm build && pnpm test:prepare

RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "nuxt maxbug source" && git tag baseline

CMD ["node", "-e", "console.log('nuxt', require('/nuxt/packages/nuxt/package.json').version)"]
