# Maximally-buggy dayjs — frozen at candidate anchor version v1.8.32.
#
# Built upstream by `pandora construct build-image -t dayjs@1.8.32`, which prepares the build
# context under data/dayjs/maxbug/1.8.32/context/: it exports the dayjs source tree at tag
# v1.8.32 FROM THE LOCAL CLONE (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md) into ./dayjs, and copies this file in as
# ./Dockerfile.
#
# Why v1.8.32: dayjs' coverage curve peaks at 37 live subtasks across v1.8.24 (2020-04) to
# v1.8.32 (2020-08), and v1.8.32 is the latest tag at the peak — at equal coverage the
# later anchor sits closer to the fixes whose patches have to apply to it.
#
# Why node 10 + full-icu: dayjs' `timezone` and `utc` plugins read `Intl.DateTimeFormat`
# for the whole zone database, so the suite's outcome is a function of the node build and
# its ICU data. Measured on pristine images (524 tests):
#
#   node 14 (ICU 70.1, full ICU in the box)   522 pass, **2 fail**
#   node 10 + full-icu@1.4.0 (ICU 64.2)       see below
#
# Both node-14 failures are in test/plugin/timezone.test.js and both are DST-transition
# cases at America/New_York — the `hour12`/`hourCycle` behaviour that ICU changed after
# this tag, which dayjs only fixed later. Since the timezone plugin is a large share of
# this task's bug population, a pristine failure there is not acceptable, so the base is
# node 10 with the `full-icu` data package: upstream's own CI matrix at this tag was node
# 8/10/12.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/iamkun/dayjs.git /src \
 && git -C /src checkout --quiet v1.8.32 \
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

# ICU data for node 10's small-icu build: without it the whole `timezone`/`utc` plugin
# suite fails before any patch is applied, which would read as `fails_pre_gold`.
RUN npm install --no-save --prefix / full-icu@1.4.0
ENV NODE_ICU_DATA=/node_modules/full-icu

# dayjs' `npm test` runs the suite four times under four zones and then once more under
# the CI default. The census runs one targeted file at a time, so it gets the default —
# pin it to UTC, which is what upstream's CI had.
ENV TZ=UTC \
    LANG=en_US.utf8 \
    CI=yes

# dayjs source tree at the candidate tag, exported from the local clone into the build
# context (see the header).
COPY --from=swesweep-src /src /dayjs
WORKDIR /dayjs

# There is no lockfile in the tree at this tag — upstream's CI ran a plain `npm install`,
# so that is what this does. `--ignore-scripts` skips the `pre-commit` package's install
# hook, which wants to write git hooks into a tree that is not a repo yet.
RUN npm install --ignore-scripts

# Make the exported tree a git repo, commit the source and tag it `baseline`.
# `node_modules/` is in dayjs' own .gitignore, so it is NOT part of the baseline commit
# and the consumers' `git reset --hard baseline && git clean -fdq` (no -x) leaves the
# installed dependencies alone.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "dayjs maxbug source" && git tag baseline

CMD ["node", "-e", "console.log('dayjs', process.versions.icu, process.versions.cldr)"]
