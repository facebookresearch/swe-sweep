# Maximally-buggy prettier — frozen at anchor version 3.3.3.
#
# Built upstream by `pandora construct build-image -t prettier@3.3.3`, which prepares the build
# context from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the prettier source tree at
# 3.3.3 into ./prettier and copies this file in as ./Dockerfile. The image holds the
# prettier git tree with a `baseline` commit+tag; the host-controlled evaluator
# (tasks/prettier/task.yaml) does `git reset --hard baseline`, then applies the
# per-bug test/gold patches.
#
# There is NO transpile step. `scripts/build/build.js` exists but only produces the
# published `dist/`; the suite resolves prettier through `tests/config/` straight out of
# `src/` unless `PRETTIER_DIR` says otherwise. So a gold patch is live the moment it applies
# and the runner passes needs_build=False.
#
# **The package manager is vendored, and that is what keeps the image period-correct.** The
# tree carries yarn 4.3.1 in `.yarn/releases/` and points `.yarnrc.yml` at it, so the
# install runs that exact yarn against the committed `yarn.lock` — `npm install` would
# re-resolve every range against today's registry and quietly change what the tests observe.
#
# **The Node patch level is pinned, not just the major.** Node 20.17 backported
# `require(esm)`, which changes which branch of jest's `requireOrImportModule` loads
# `jest.config.js`: on 20.17+ it takes `require()` and dies with `ERR_REQUIRE_ASYNC_MODULE`,
# because prettier's config is an ES module with top-level await. 20.15 is what was current
# when 3.3.3 shipped, and it takes the `import()` branch the repo was written against.
#
# Why not the curve peak: it is 1.15.1 (Nov 2018) at 126 live subtasks against 3.3.3's 80.
# That tree keeps its fixture harness in top-level `tests_config/` and `tests_integration/`
# and runs on the Node 8 era's jest, and freezing there would trade a suite the benchmark
# already has an adapter for against a bespoke one. The 2.x line (2.0.1, 86 live) has the
# same top-level harness layout.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/prettier/prettier.git /src \
 && git -C /src checkout --quiet 3.3.3 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM node:20.15-bookworm-slim
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# git supports the host-directed reset/apply between instances. prettier links against no
# system library, so that is the whole list.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends git ca-certificates; \
    rm -rf /var/lib/apt/lists/*

# prettier's own `test` script passes this on the command line; setting it in the
# environment is what makes it reach the suite when the runner invokes jest directly rather
# than through yarn. The tree is ESM (`"type": "module"`) and jest needs the flag to load it.
ENV NODE_OPTIONS=--experimental-vm-modules

# prettier source tree at the anchor ref, exported from the local clone into the build
# context (see the header).
COPY --from=swesweep-src /src /prettier
WORKDIR /prettier

# The vendored yarn, against the committed lockfile. `--immutable` fails rather than
# silently rewriting `yarn.lock` if the tree and the lockfile disagree. `corepack` is what
# node:20 ships to run the pinned `packageManager`, and it must not try to fetch a release
# it already has in `.yarn/releases/`.
RUN corepack enable && yarn install --immutable

# Make the exported tree a git repo (the export carries no .git), commit the source and tag
# it `baseline`. node_modules/ and .yarn/cache are gitignored by the tree's own .gitignore,
# so the install stays out of the baseline commit and survives the runner's `git clean -fdq`
# (which is deliberately not `-fdx`).
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "prettier maxbug source" && git tag baseline

# Prove the suite is green before any patch is applied: a pristine failure reads as
# fails_pre_gold and quietly inflates the census with subtasks that reproduce nothing. One
# untouched format directory, which exercises the whole snapshot harness that nearly every
# subtask runs through.
RUN node --experimental-vm-modules node_modules/jest/bin/jest.js \
        --ci --runInBand --coverage=false tests/format/json/json

CMD ["node", "-e", "import('./src/index.js').then(m => console.log('prettier', m.default.version))"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
