# Maximally-buggy F# — frozen at main 15b5a6ce4b (2024-08-07).
#
# Built upstream by `pandora construct build-image -t fsharp@main-20240807`, which prepares the build
# context from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the F# source tree at that commit
# into ./fsharp and copies this file in as ./Dockerfile. The image holds the tree with a
# `baseline` commit+tag; the host-controlled evaluator (tasks/fsharp/task.yaml)
# does `git reset --hard baseline`, then applies the per-bug test/gold patches and rebuilds.
#
# **The anchor is a main commit, not a release tag.** No `dotnet/fsharp` tag is an ancestor
# of `main` — each one is cut on a release branch for a Visual Studio or SDK band — so a tag
# is a maintenance tip in the sense of docs/ai/040-experiments/nim/, and the fixes the crawl
# finds all land on `main`. This is the peak of the coverage curve (149 live subtasks); measured attrition here is
# 43% of the fixes merged in the next three months.
#
# Three things are specific to a .NET repository:
#
# 1. **The build brings its own SDK.** Arcade (`eng/common/tools.sh`) downloads the exact
#    SDK `global.json` pins into `./.dotnet` and builds with that, so the base image's SDK
#    only has to be new enough to bootstrap the scripts. `.dotnet`, `artifacts` and the
#    NuGet cache are all gitignored, so the `git clean` between subtasks leaves them and the
#    per-subtask rebuild stays incremental.
#
# 2. **Restore has to happen while the network is still there.** The census container has
#    none, so the image restores once and the per-subtask rebuild is `--norestore`.
#
# 3. **`dotnet test` writes no report unless asked.** The runner passes the `trx` logger;
#    nothing here has to arrange that.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/dotnet/fsharp.git /src \
 && git -C /src checkout --quiet 15b5a6ce4b \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM mcr.microsoft.com/dotnet/sdk:8.0
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# NoWarn as an *environment* property, not `/p:`. Arcade restores its own `Tools.proj`
# in a separate MSBuild invocation that never sees the command line, and its pinned
# 2023-preview tool packages are no longer on the feed at the exact version, so NuGet
# resolves a near one and NU1603 fails the restore. An environment property reaches
# every invocation and — unlike a command-line global property — a project can still
# add to it, which is what keeps this tree's per-project NoWarn lists working.
ENV NoWarn=NU1603 \
    TreatWarningsAsErrors=false \
    DEBIAN_FRONTEND=noninteractive \
    DOTNET_CLI_TELEMETRY_OPTOUT=1 \
    DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1 \
    DOTNET_NOLOGO=1 \
    DOTNET_SYSTEM_GLOBALIZATION_INVARIANT=0
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends git curl ca-certificates locales; \
    rm -rf /var/lib/apt/lists/*

# F# source tree at the anchor commit, exported from the local clone into the build context
# (see the header).
COPY --from=swesweep-src /src /fsharp
WORKDIR /fsharp

# Make the exported tree a git repo (the export carries no .git), commit the source and tag
# it `baseline`. The branch is `main`, not `baseline`: a branch and a tag of the same name
# make every `git reset --hard baseline` warn about an ambiguous refname.
# The remote is not there to be fetched from: Arcade builds with SourceLink, and
# `Microsoft.Build.Tasks.Git` fails the build outright with "Repository '/fsharp' has no
# remote" if the tree it is building is a git repo without one.
RUN git init -q -b main \
    && git config user.email v@x && git config user.name v \
    && git remote add origin https://github.com/dotnet/fsharp.git \
    && git add -A && git commit -q -m "fsharp maxbug source" && git tag baseline

# One script for both the image build and the per-subtask rebuild, so the flags cannot drift
# apart. The image build passes `--restore`; the rebuild does not, because by then there is
# no network.
RUN set -eux; \
    printf '%s\n' \
      '#!/bin/sh' \
      'set -eu' \
      'cd /fsharp' \
      '# SourceLink wants a real commit on a real remote; this tree has neither. The' \
      '# arcade wrapper only forwards `/p:` to MSBuild -- it rejects `-p:` outright.' \
      'SL="/p:EnableSourceLink=false /p:EnableSourceControlManagerQueries=false /p:DeterministicSourcePaths=false"' \
      '# NU1603 is handled by the NoWarn *environment* property set in the image, not here:' \
      '# a command-line /p: is an MSBuild global property, and a global property cannot be' \
      '# reassigned by a project, so /p:NoWarn would silently discard every per-project' \
      '# NoWarn list in this tree and the build would die on 379 escalated FS0044 notices.' \
      '# shellcheck disable=SC2086' \
      './build.sh --build --configuration Release $SL "$@"' \
      > /usr/local/bin/fsharp-build; \
    chmod +x /usr/local/bin/fsharp-build

RUN fsharp-build --restore

CMD ["dotnet", "--info"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
