# Maximally-buggy stylelint — frozen at anchor version 16.9.0.
#
# Built upstream by `pandora construct build-image -t stylelint@16.9.0`, which prepares the build
# context from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the stylelint source tree at
# 16.9.0 into ./stylelint and copies this file in as ./Dockerfile. The image holds the
# stylelint git tree with a `baseline` commit+tag; the host-controlled evaluator
# (tasks/stylelint/task.yaml) does `git reset --hard baseline`, then applies the
# per-bug test/gold patches.
#
# There is NO transpile step. stylelint ships lib/ as plain JavaScript — .mjs for the
# library, .cjs for the CommonJS entry points — so a gold patch is live the moment it
# applies and the runner passes needs_build=False. That is what makes this one of the
# cheapest images in the JS cohort: `npm ci` is the whole build.
#
# The runner-up candidate. 16.9.0 (Aug 2024) is the far end of the same plateau: 97 live
# subtasks against 16.6.1's 108, but 74 with both patches applying against 73. It is built
# so the census can decide between the two on what actually reproduces, rather than on an
# apply rate that separates them by one.
# Measured in docs/ai/040-experiments/stylelint/260820-anchor-choice.md.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/stylelint/stylelint.git /src \
 && git -C /src checkout --quiet 16.9.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM node:20-bookworm-slim
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# git supports host-directed reset/apply. Python remains available for package build tools.
# stylelint itself links against no system
# library, so that is the whole list.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends git ca-certificates python3; \
    ln -sf /usr/bin/python3 /usr/local/bin/python; \
    rm -rf /var/lib/apt/lists/*

# jest needs this to load an ESM test module, and stylelint's tree is ESM by extension
# (.mjs) with no `"type": "module"` to announce it. The repo's own `npm test` script
# passes the same flag on the command line; setting it in the environment is what makes it
# reach the suite when the runner invokes jest directly rather than through npm.
ENV NODE_OPTIONS=--experimental-vm-modules

# stylelint source tree at the anchor ref, exported from the local clone into the build
# context (see the header).
COPY --from=swesweep-src /src /stylelint
WORKDIR /stylelint

# `npm ci` installs exactly the package-lock.json the tag committed, which is what keeps
# the image period-correct: `npm install` would re-resolve every caret range against
# today's registry and quietly change what the tests observe. There is no lockfile drift
# to worry about — stylelint commits one.
RUN npm ci --no-audit --no-fund

# Make the exported tree a git repo (the export carries no .git), commit the source and
# tag it `baseline`. node_modules/ is gitignored by the tree's own .gitignore, so the
# install stays out of the baseline commit and survives the runner's `git clean -fdq`
# (which is deliberately not `-fdx`).
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "stylelint maxbug source" && git tag baseline

# Prove the suite is green before any patch is applied: a pristine failure reads as
# fails_pre_gold and quietly inflates the census with subtasks that reproduce nothing.
# One untouched rule's tests, which exercises the whole testRule harness.
RUN node --experimental-vm-modules node_modules/jest/bin/jest.js \
        --ci --runInBand --coverage=false lib/rules/color-no-invalid-hex

CMD ["node", "-e", "import('./lib/index.mjs').then(m => console.log('stylelint', m.default.utils ? 'ok' : 'ok'))"]
