# Maximally-buggy luxon — frozen at candidate anchor version 1.20.0.
#
# Built upstream by `pandora construct build-image -t luxon@1.20.0`, which prepares the build
# context under data/luxon/maxbug/1.20.0/context/: it exports the luxon source tree at
# tag 1.20.0 FROM THE LOCAL CLONE (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md) into ./luxon, and copies this file in as
# ./Dockerfile.
#
# Why 1.20.0: luxon's coverage curve has a flat top of 20 live subtasks running from
# 1.6.0 (2018-11) to 1.20.0 (2019-10), and 1.20.0 is the *latest* tag on that plateau.
# Later is better at equal coverage — the anchor sits closer to the fixes whose patches
# have to apply to it, and to a dependency graph npm can still resolve.
#
# ## Why the environment below is load-bearing
#
# luxon ships **no** tz or locale tables. Every zone conversion and every formatted string
# comes out of the host's `Intl`, so the suite's expected output is a function of the node
# build, its ICU/CLDR data and the container's zone. Upstream knew this and shipped its own
# test image (`docker/Dockerfile` at the tag); this reproduces it:
#
#     FROM library/node:10-slim
#     RUN npm install full-icu
#     ENV NODE_ICU_DATA=/node_modules/full-icu
#     ENV LANG=en_US.utf8
#     ENV CI=yes
#     ENV TZ=America/New_York
#
#   * NODE_ICU_DATA — node 10 ships *small* ICU (English only), and without the locale
#     data roughly the whole formatting and zone suite fails before any patch is applied,
#     which reads as `fails_pre_gold` and inflates the census with subtasks that reproduce
#     nothing.
#   * TZ — `Local` is the container's zone, and test/datetime/dst.test.js asserts against
#     America/New_York offsets.
#   * LANG — the default locale the tests format against.
#
# ## The node version was measured, not assumed
#
# Pristine full-suite runs of this image (894 tests):
#
#   node 10 + full-icu (ICU 64.2 / CLDR 35.1)   878 pass ... 892 pass, **2 fail**
#   node 14 (ICU 70.1 / CLDR 40, full ICU)                   878 pass, **16 fail**
#
# node 14 is the newer, tidier image — no `full-icu` package needed — but a further five
# years of CLDR churn has moved the zone display names and relative-time strings the suite
# asserts on, and it breaks six suites including test/datetime/dst.test.js. node 10 is kept
# for that reason.
#
# Its two remaining failures are both in test/datetime/toFormat.test.js and are the same
# difference: CLDR 35 formats a French time with an unpadded hour ("9:23:54") where the
# test at this tag expects "09:23:54". **No subtask in the population targets that file**
# (the distribution over the 51 skim-accepted subtasks is format.test.js 10,
# duration/format.test.js 7, tokenParse.test.js 7, ...), so the census is unaffected.
#
# The non-slim `node:10` is used rather than `node:10-slim` because it already carries git
# (the baseline commit below needs it), and Debian buster's apt archive has since moved,
# so `apt-get install git` in the slim image is not reliably reachable.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/moment/luxon.git /src \
 && git -C /src checkout --quiet 1.20.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM docker.io/library/node:10
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# ICU data for node 10's small-icu build (see the header).
RUN npm install --no-save --prefix / full-icu@1.4.0
ENV NODE_ICU_DATA=/node_modules/full-icu

ENV LANG=en_US.utf8 \
    TZ=America/New_York \
    CI=yes

# luxon source tree at the candidate tag, exported from the local clone into the build
# context (see the header).
COPY --from=swesweep-src /src /luxon
WORKDIR /luxon

# `--ignore-scripts` skips husky's `install` hook, which tries to write git hooks into a
# tree that is not a repo yet (the export carries no .git) and fails the build. Nothing
# the suite needs is built by a lifecycle script — jest and babel-jest are plain JS.
RUN npm ci --ignore-scripts

# Make the exported tree a git repo, commit the source and tag it `baseline`. Both
# `node_modules/` and `build/` are in luxon's own .gitignore, so they are NOT part of the
# baseline commit and the consumers' `git reset --hard baseline && git clean -fdq` (no -x)
# leaves the installed dependencies alone.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "luxon maxbug source" && git tag baseline

CMD ["node", "-e", "console.log('luxon', require('./package.json').version, process.versions.icu, process.versions.cldr)"]
