# Maximally-buggy DataFrames.jl — frozen at anchor version v1.1.0.
#
# Built upstream by `pandora construct build-image -t dataframes-jl@1.1.0`, which prepares the build
# context under data/dataframes-jl/maxbug/1.1.0/context/: it exports the source tree at
# v1.1.0 FROM THE LOCAL CLONE (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md) into ./dataframes, and copies this file in as
# ./Dockerfile. The image holds the git tree with a `baseline` commit+tag; the in-container
# validator (tasks/dataframes-jl/task.yaml) does `git reset --hard baseline`, then
# applies the per-bug test/gold patches.
#
# Why 1.1.0 (May 2021): the coverage curve peaks at 23 live subtasks at the end of May 2021,
# and v1.1.0 is the release sitting in that run with 22 — tied with v1.0.0 on coverage and
# on patch-applies (15 test / 15 gold), and the closer of the two to the peak.
#
# Why Julia 1.6: period-correct for a May-2021 release, and the minimum DataFrames 1.x
# supports.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/JuliaData/DataFrames.jl.git /src \
 && git -C /src checkout --quiet v1.1.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM docker.io/library/julia:1.6-bullseye
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# git supports host-directed reset/apply. Python remains available for repository tooling.
# With FwdProxy in front of apt, apt's unprivileged `_apt` sandbox user can't read the
# proxied download, so let apt run as root first.
RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    apt-get update; \
    apt-get install -y --no-install-recommends git ca-certificates python3 python-is-python3; \
    rm -rf /var/lib/apt/lists/*

# Source tree at the anchor ref, exported from the local clone into the build context.
COPY --from=swesweep-src /src /dataframes
WORKDIR /dataframes

# Make the exported tree a git repo (the export carries no .git), commit the source and tag
# it `baseline`. Julia compiles on load and writes nothing into the source tree, so the tree
# is source all the way down and an extracted patch is clean by construction.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "dataframes maxbug source" && git tag baseline

# A depot inside the image, so the dependency downloads and precompile caches are baked in
# rather than re-fetched per subtask — the reproduce container runs with `--network=none`.
ENV JULIA_DEPOT_PATH=/depot

# Pre-warm: resolve and precompile the *test* environment (deps plus the `[targets] test`
# extras), which is what `Pkg.test()` builds and what the runner needs offline later.
#
# The suite is deliberately allowed to fail: this is the maximally-buggy commit, so red
# tests are the expected state and gating the build on them would be wrong. The point of
# the run is the environment it leaves behind in /depot; the next step is the real gate.
# This is the slowest pre-warm of the cohort — DataFrames' suite is the largest of the
# three and takes minutes.
RUN julia -e 'using Pkg; Pkg.activate("/dataframes"); Pkg.instantiate(); \
    try; Pkg.test(); catch e; @warn "pre-warm suite failed (expected at a buggy anchor)"; end'

# The actual build gate: the package must load and the test environment must be complete.
# A missing test-only dependency would otherwise only surface per-subtask, as a load error.
RUN julia --project=/dataframes -e 'using DataFrames; println("DataFrames loads OK")' \
    && julia --project=/dataframes -e 'using Pkg; Pkg.status()'

# Offline from here on: the reproduce/eval containers get `--network=none`, so Pkg must
# resolve purely from what the pre-warm installed. Set after the pre-warm on purpose —
# earlier it would have blocked the downloads above.
ENV JULIA_PKG_OFFLINE=true

CMD ["julia", "--project=/dataframes", "-e", "using DataFrames; println(\"DataFrames OK\")"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
