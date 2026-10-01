# Maximally-buggy babel — frozen at anchor v7.0.0.
#
# Built upstream by `pandora construct build-image -t babel@7.0.0`, which prepares the build context
# from the local clone (no GitHub access — see docs/ai/010-design/005-style-conventions.md):
# it exports the source tree at v7.0.0 into ./babel and copies this file in as ./Dockerfile.
# The image holds the tree with a `baseline` commit+tag; the host-controlled evaluator
# (tasks/babel/task.yaml) does `git reset --hard baseline`, then applies the per-bug
# test/gold patches.
#
# Why v7.0.0: babel 6 -> 7 renamed every `babel-*` package to `@babel/*` and moved the tree,
# so a patch from either side cannot cross it — the whole candidate range is 7.x. 7.0.0 is
# where the probe turns over: 90 subtasks with both patches applying, against 87 at
# 7.0.0-beta.51 below and 82 at 7.1.5 / 78 at 7.4.5 above. `v7.0.0-rc.2` scores 93, but a
# release candidate is not a release and three subtasks is not worth freezing on one. See
# docs/ai/040-experiments/babel/260819-anchor-choice.md.
#
# Why Node 10: v7.0.0's own `engines.node` is `>= 6.9.0 <= 11.0.0-0`, and its gulp/babel-
# register toolchain of that era does not run on newer majors.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/babel/babel.git /src \
 && git -C /src checkout --quiet v7.0.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM node:10-buster
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# git supports host-directed reset/apply. Python remains available for package build tools.
#
# buster is out of support, so its apt sources have moved to the archive; without this the
# very first `apt-get update` 404s and the image cannot be built at all.
RUN set -eux; \
    sed -i 's|deb.debian.org/debian|archive.debian.org/debian|g; \
            s|security.debian.org/debian-security|archive.debian.org/debian-security|g; \
            /buster-updates/d' /etc/apt/sources.list; \
    apt-get -o Acquire::Check-Valid-Until=false update; \
    apt-get install -y --no-install-recommends git ca-certificates python3; \
    ln -sf /usr/bin/python3 /usr/local/bin/python; \
    rm -rf /var/lib/apt/lists/*

# Host-driven evaluation supplies complete commands, so do not let the base image prepend `node`.
ENTRYPOINT []

COPY --from=swesweep-src /src /babel
WORKDIR /babel

# **This tree is not a yarn workspace.** The root package.json declares no `workspaces` key;
# v7.0.0 links its packages to each other with `lerna bootstrap` (see the Makefile's own
# `bootstrap` target), and lerna is what creates `node_modules/@babel/*` as symlinks into
# `packages/`. Without the second command every fixture driver dies on
# `Cannot find module '@babel/helper-fixtures'` before a single test runs — which reads as a
# collection error and costs every fixture-driven subtask, i.e. nearly all of them.
#
# `--frozen-lockfile` at the root is what makes that half period-correct: the committed
# yarn.lock decides every version, not today's registry. lerna's own client args are
# `--no-lockfile` (lerna.json), which is the repo's choice, not ours.
#
# `--ignore-engines` because a transitive dependency declares an engine range this Node 10
# does not satisfy; babel's own bootstrap passes the same flag on both halves.
RUN yarn install --frozen-lockfile --ignore-engines --network-timeout 600000 \
    && ./node_modules/.bin/lerna bootstrap -- --ignore-engines --network-timeout 600000

# Compile every package. babel's tests import each package's built `lib/`, not its `src/`, so
# an unbuilt tree fails every test on an unresolved import rather than on the bug under test.
#
# `gulp build` directly rather than `make build`: the Makefile target additionally builds
# babel-standalone and babel-preset-env-standalone (two browser bundles, several minutes
# each) and regenerates the flow/typescript typings, none of which any test imports. It also
# starts with `clean`, which would throw away nothing here and cost a full rebuild.
#
# The generateTypeHelpers + second gulp pass IS kept: babel-types' helpers are generated from
# its own definitions and then have to be compiled, and babel-traverse — 50 of this anchor's
# subtasks — imports them.
ENV NODE_OPTIONS=--max-old-space-size=4096
RUN ./node_modules/.bin/gulp build \
    && node ./packages/babel-types/scripts/generateTypeHelpers.js \
    && ./node_modules/.bin/gulp build

RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "babel maxbug source" && git tag baseline

CMD ["node", "-e", "console.log('babel', require('/babel/package.json').version)"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
