# Maximally-buggy webpack — frozen at anchor v5.60.0.
#
# Built upstream by `pandora construct build-image -t webpack@5.60.0`, which prepares the build
# context from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the source tree at v5.60.0 into
# ./webpack and copies this file in as ./Dockerfile. The image holds the tree with a
# `baseline` commit+tag; the host-controlled evaluator (tasks/webpack/task.yaml) does
# `git reset --hard baseline`, then applies the per-bug test/gold patches.
#
# Why v5.60.0: webpack 4 -> 5 rewrote `lib/` wholesale, so the whole candidate range is 5.x,
# and 5.60.0 is the interior maximum of the patch-applies probe — 44 subtasks with both
# patches applying, against 43 at 5.66.0, 39 at 5.55.0 and 35 at 5.50.0. See
# docs/ai/040-experiments/webpack/260819-anchor-choice.md.
#
# Why Node 16: v5.60 (October 2021) declares `engines.node >= 10.13.0` and its CI of the era
# ran 10/12/14/16. 16 is the newest of those, so it is the one still able to install the
# lockfile's native dependencies.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/webpack/webpack.git /src \
 && git -C /src checkout --quiet v5.60.0 \
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

# git supports host-directed reset/apply. Python remains available for package build tools.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends git ca-certificates python3; \
    ln -sf /usr/bin/python3 /usr/local/bin/python; \
    rm -rf /var/lib/apt/lists/*

# Host-driven evaluation supplies complete commands, so do not let the base image prepend `node`.
ENTRYPOINT []

COPY --from=swesweep-src /src /webpack
WORKDIR /webpack

# yarn-1, and `--frozen-lockfile` is what makes the install period-correct: the committed
# yarn.lock decides every version, not today's registry.
RUN yarn install --frozen-lockfile --network-timeout 600000

# **No build step.** webpack ships the `lib/*.js` it runs; there is no compile between a gold
# patch and the test that exercises it, which is why the runner passes `needs_build=False`.

# webpack's own test script runs node with these two flags, and the suite needs both: the
# ESM cases fail to load without `--experimental-vm-modules`, and the config corpus exhausts
# the default heap. Setting them here rather than in the runner keeps them with the image
# they are period-correct for.
ENV NODE_OPTIONS="--experimental-vm-modules --max-old-space-size=4096"

RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "webpack maxbug source" && git tag baseline

CMD ["node", "-e", "console.log('webpack', require('/webpack/package.json').version)"]
