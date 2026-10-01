# Maximally-buggy svgo — frozen at anchor version v3.0.2.
#
# Built upstream by `pandora construct build-image -t svgo@v3.0.2`, which prepares the build context
# from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the svgo source tree at v3.0.2
# into ./svgo and copies this file in as ./Dockerfile. The image holds the svgo git tree
# with a `baseline` commit+tag; the host-controlled evaluator
# (tasks/svgo/task.yaml) does `git reset --hard baseline`, then applies the
# per-bug test/gold patches.
#
# There is NO transpile step. svgo ships lib/ and plugins/ as plain CommonJS and only uses
# rollup for the browser bundle, so a gold patch is live the moment it applies and the
# runner passes needs_build=False.
#
# **The package manager is vendored, and that is what keeps the image period-correct.** The
# tree carries yarn 3.2.3 in `.yarn/releases/` and points `.yarnrc.yml` at it, so the
# install runs that exact yarn against the committed `yarn.lock` — `npm install` would
# re-resolve every caret range against today's registry and quietly change what the tests
# observe. `nodeLinker: node-modules` is already set in the tree, so the install produces
# an ordinary node_modules/ that jest can resolve from.
#
# Why v3.0.2: the coverage curve peaks at 26 live subtasks on 2022-11-11, and v3.0.2 (Nov
# 2022) is the highest released tag on that plateau at 25.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/svg/svgo.git /src \
 && git -C /src checkout --quiet v3.0.2 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM node:18-bookworm-slim
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# git supports the host-directed reset/apply between instances. svgo links against no
# system library, so that is the whole list.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends git ca-certificates; \
    rm -rf /var/lib/apt/lists/*

# svgo's own `test` script passes this on the command line; setting it in the environment is
# what makes it reach the suite when the runner invokes jest directly rather than through
# yarn.
ENV NODE_OPTIONS=--experimental-vm-modules

# svgo source tree at the anchor ref, exported from the local clone into the build context
# (see the header).
COPY --from=swesweep-src /src /svgo
WORKDIR /svgo

# The vendored yarn, against the committed lockfile. `--immutable` fails rather than
# silently rewriting `yarn.lock` if the tree and the lockfile disagree.
RUN node .yarn/releases/yarn-3.2.3.cjs install --immutable

# Make the exported tree a git repo (the export carries no .git), commit the source and tag
# it `baseline`. node_modules/ is gitignored by the tree's own .gitignore, so the install
# stays out of the baseline commit and survives the runner's `git clean -fdq` (which is
# deliberately not `-fdx`).
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "svgo maxbug source" && git tag baseline

# Prove the suite is green before any patch is applied: a pristine failure reads as
# fails_pre_gold and quietly inflates the census with subtasks that reproduce nothing. The
# plugin-corpus driver is the one nearly every subtask runs through, so it is what is
# checked here.
RUN node node_modules/jest/bin/jest.js --ci --runInBand --coverage=false \
        test/plugins/_index.test.js

CMD ["node", "-e", "console.log('svgo', require('./package.json').version)"]
