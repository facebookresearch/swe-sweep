# Maximally-buggy Roslyn — frozen at the `NET-SDK-10.0.100` tag (2025-09), the recent
# anchor candidate. Same recipe as the other candidates; only the exported tree differs.
#
# Built upstream by `pandora construct build-image -t roslyn@10.0.100`, which prepares the build
# context from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the Roslyn source tree at that
# tag into ./roslyn and copies this file in as ./Dockerfile. The image holds the tree with
# a `baseline` commit+tag; the host-controlled evaluator (tasks/roslyn/task.yaml)
# does `git reset --hard baseline`, applies the per-bug test/gold patches, and rebuilds.
#
# Four things are specific to a Roslyn task:
#
# 1. **The build installs its own SDK, and it is not this image's.** Roslyn pins an exact
#    SDK build in `global.json` (usually a preview) and Arcade's `eng/common/tools.sh`
#    downloads that exact build into `<repo>/.dotnet`. The base image's SDK only has to be
#    new enough to satisfy nothing at all — what it really provides is the native
#    dependencies (ICU, OpenSSL, the compression libraries) that a .NET host needs. So
#    `/roslyn/.dotnet` goes on PATH *ahead* of the base image's, and multi-level lookup is
#    off: a `dotnet build` that picked the system SDK would be refused by `global.json`.
#
# 2. **Only `Compilers.slnf` is built.** That solution filter is `eng/build.sh`'s own
#    default, and it is exactly the graded scope — the C# and VB compilers, the
#    `Microsoft.CodeAnalysis` object model and their test projects. The rest of the
#    repository is the Visual Studio IDE stack, much of which does not build off Windows.
#
# 3. **Restore happens here, once.** The census container has no network, and NuGet would
#    otherwise try to reach the dnceng feeds for every subtask. `.packages/` (Roslyn's
#    repo-local global packages folder), `.dotnet/` and `artifacts/` are all covered by
#    Roslyn's own .gitignore, so the runner's `git reset --hard baseline` and
#    `git clean -fdq` between subtasks leave them in place and the per-subtask build is
#    both incremental and offline.
#
# 4. **There is no separate build step in the runner.** `dotnet test <project>` builds the
#    project and every project it references, so the one invocation compiles the gold
#    patch into the compiler and then runs the test that was added against it. That is why
#    `task.yaml` sets `needs_build: false` — a preceding build would be the same work
#    done twice.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/dotnet/roslyn.git /src \
 && git -C /src checkout --quiet NET-SDK-10.0.100 \
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

ENV DEBIAN_FRONTEND=noninteractive
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        git curl ca-certificates unzip; \
    rm -rf /var/lib/apt/lists/*

# Roslyn source tree at the anchor tag, exported from the local clone into the build
# context (see the header).
COPY --from=swesweep-src /src /roslyn
WORKDIR /roslyn

# Make the exported tree a git repo (the export carries no .git), commit the source and
# tag it `baseline`. This has to happen *before* the build, so that everything the build
# downloads and produces stays untracked — and therefore survives the runner's reset
# between subtasks.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "roslyn maxbug source" && git tag baseline

ENV DOTNET_CLI_TELEMETRY_OPTOUT=1 \
    DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1 \
    DOTNET_NOLOGO=1 \
    DOTNET_MULTILEVEL_LOOKUP=0 \
    DOTNET_ROOT=/roslyn/.dotnet \
    PATH=/roslyn/.dotnet:/usr/share/dotnet:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    NUGET_PACKAGES=/roslyn/.packages

# **NU1603 has to stop being an error, or no historical tag builds.** Arcade's toolset
# project asks for its sibling build tasks (SignTool, NuGetRepack, Build.Tasks.Feed) at
# the *exact* beta version this tag pinned; some of those daily builds were never pushed
# to the public dnceng feed, so NuGet resolves the nearest one, warns NU1603 — and the
# toolset project treats its warnings as errors. This is a property of the age of the tag,
# not of the tag: it will hit every candidate. MSBuild reads environment variables as
# properties, which is the only way to reach the toolset restore — it runs before any
# command line of ours is in play.
ENV NoWarn=NU1603 \
    WarningsNotAsErrors=NU1603

# Restore and build the compilers. `--ci` is deliberately *not* passed: it turns on
# deterministic-build and telemetry behaviour meant for a throwaway CI agent, and it
# cleans up the very state (the build server, the toolset) that makes the next build
# incremental.
RUN ./eng/build.sh --restore --build --configuration Release --solution Compilers.slnf /p:RestoreDisableParallel=true

# A warm build server would hold the compiler DLLs the next build wants to overwrite.
RUN /roslyn/.dotnet/dotnet build-server shutdown || true

CMD ["/roslyn/.dotnet/dotnet", "--info"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
