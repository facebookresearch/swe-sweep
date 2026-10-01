# Maximally-buggy isomorphic-git — frozen at candidate anchor version v1.9.0.
#
# Built upstream by `pandora construct build-image -t isomorphic-git@v1.9.0`, which prepares the
# build context from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the source tree at v1.9.0 into
# ./isomorphic-git and copies this file in as ./Dockerfile. The image holds the tree with
# a `baseline` commit+tag; the host-controlled evaluator
# (tasks/isomorphic-git/task.yaml) does `git reset --hard baseline`, then
# applies the per-bug test/gold patches.
#
# Why v1.9.0: it is the single peak of the SZZ coverage curve — 29 live subtasks on
# 2021-07-02, on a plateau of 27-28 that runs from 2020-09 to 2022-01.
#
# Why Node 10: `azure-pipelines.yml` pins `versionSpec: '10.x'`, and it has to. The tree's
# `package.json` sets `"type": "module"` while `jest.config.js` is CommonJS, so from Node
# 12 onwards `require()`-ing the config dies with ERR_REQUIRE_ESM and jest cannot start at
# all. Node 10 predates ESM detection, reads the config as CommonJS, and ships the npm 6
# that `package-lock.json` (lockfileVersion 1) was written by.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/isomorphic-git/isomorphic-git.git /src \
 && git -C /src checkout --quiet v1.9.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM docker.io/library/node:10-buster
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# **No `apt-get` here.** Debian buster is end-of-life and `deb.debian.org` now 404s for
# it (the packages moved to archive.debian.org), so any `apt-get update` in this image
# fails. It is not needed either: the full `node:10-buster` image already carries `git`,
# `ca-certificates` and the `python` that node-gyp wants.

# Host-driven evaluation supplies complete commands, so do not let the base image prepend
# `node`.
ENTRYPOINT []

COPY --from=swesweep-src /src /isomorphic-git
WORKDIR /isomorphic-git

# `npm ci` rather than `npm install`: the lockfile is what makes the install
# period-correct, and the census container has no network so everything has to be here
# already.
#
# `PUPPETEER_SKIP_CHROMIUM_DOWNLOAD` is not an optimisation. puppeteer 2.0.0 is a
# devDependency (the karma/browser half of CI, which is out of scope here) and its
# postinstall downloads a ~100 MB Chromium from storage.googleapis.com; that host is not
# reachable from the build sandbox, so without this the whole install fails.
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true \
    npm_config_fund=false \
    npm_config_audit=false
RUN npm ci --no-optional

# **No build step.** `jest.config.js` maps the package's own name straight at the source
# tree (`'^isomorphic-git$': '<rootDir>/src'`), so the suite exercises `src/` directly and
# a gold patch takes effect with no rebuild — which is why the runner sets
# `needs_build: false`.

# Prove the suite is green *before* any patch is applied. A pristine failure reads as
# `fails_pre_gold` for every subtask in that file and would quietly inflate the census.
# `test-GitConfig` is pure parsing, and `test-add` exercises the fixture filesystem the
# rest of the suite is built on — if fixtures are broken, that is where it shows.
RUN npx --no-install jest --ci --runInBand --coverage=false \
        __tests__/test-GitConfig.js __tests__/test-add.js

RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "isomorphic-git maxbug source" && git tag baseline

# The census has no network, and it does not need any: the ten test files that speak HTTP
# point at `http://localhost:8888`, which is `git-http-mock-server` serving
# `__tests__/__fixtures__` — the same thing CI's `nps test.setup` starts. The runner's
# `setup_cmd` brings it up once per container session (the image's own CMD never runs,
# because the session replaces the entrypoint with a sleep loop).
CMD ["node", "-e", "console.log(require('/isomorphic-git/package.json').name)"]
