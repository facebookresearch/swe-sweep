# Maximally-buggy Distributions.jl — frozen at anchor version v0.21.6.
#
# Built upstream by `pandora construct build-image -t distributions-jl@0.21.6`, which prepares the
# build context under data/distributions-jl/maxbug/0.21.6/context/: it exports the source
# tree at v0.21.6 FROM THE LOCAL CLONE (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md) into ./distributions, and copies this file in
# as ./Dockerfile. The image holds the git tree with a `baseline` commit+tag; the
# host-controlled evaluator (tasks/distributions-jl/task.yaml) does
# `git reset --hard baseline`, then applies the per-bug test/gold patches.
#
# Why 0.21.6 (Nov 2019): it is the exact peak of the coverage curve — 32 live subtasks, the
# most of any commit in the repo's history — and it also wins the patch-applies comparison
# against the modern candidate v0.25.44 (15 test patches apply vs 12, 24 gold each).
#
# Why Julia 1.6 and not a period-correct 1.3: **the registry**. Julia gained the Pkg server
# (pkg.julialang.org, plain HTTPS) in 1.5; before that `Pkg` fetches the General registry by
# git-cloning github.com, which is unreachable from this build host even through FwdProxy,
# so a 1.3 image cannot resolve a single dependency. 1.6 is the oldest LTS that reaches the
# registry, and v0.21.6's 2019 dependency pins (SpecialFunctions 0.8, StatsBase 0.32,
# PDMats 0.9) do resolve and load under it — verified before this file was written.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/JuliaStats/Distributions.jl.git /src \
 && git -C /src checkout --quiet v0.21.6 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

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
COPY --from=swesweep-src /src /distributions
WORKDIR /distributions

# Make the exported tree a git repo (the export carries no .git), commit the source and tag
# it `baseline`. Julia compiles on load and writes nothing into the source tree, so the tree
# is source all the way down and an extracted patch is clean by construction.
#
# The commit happens BEFORE the pre-warm below, which writes a Manifest.toml into the tree:
# `baseline` must be the pristine source, and the runner's `git clean -fdq` then keeps the
# resolved manifest (it is untracked) so the offline environment survives every reset.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "distributions maxbug source" && git tag baseline

# A depot inside the image, so the dependency downloads and precompile caches are baked in
# rather than re-fetched per subtask — the reproduce container runs with `--network=none`.
ENV JULIA_DEPOT_PATH=/depot

# Pre-warm: resolve and precompile the *test* environment (deps plus the `[targets] test`
# extras), which is what `Pkg.test()` builds and what the runner needs offline later.
#
# The suite is deliberately allowed to fail: this is the maximally-buggy commit, so red
# tests are the expected state and gating the build on them would be wrong. The point of
# the run is the environment it leaves behind in /depot; the next step is the real gate.
RUN julia -e 'using Pkg; Pkg.activate("/distributions"); Pkg.instantiate(); \
    try; Pkg.test(); catch e; @warn "pre-warm suite failed (expected at a buggy anchor)"; end'

# The actual build gate: the package must load and the test environment must be complete.
# A missing test-only dependency would otherwise only surface per-subtask, as a load error.
RUN julia --project=/distributions -e 'using Distributions; println("Distributions loads OK")' \
    && julia --project=/distributions -e 'using Pkg; Pkg.status()'

# Offline from here on: the reproduce/eval containers get `--network=none`, so Pkg must
# resolve purely from what the pre-warm installed. Set after the pre-warm on purpose —
# earlier it would have blocked the downloads above.
ENV JULIA_PKG_OFFLINE=true

CMD ["julia", "--project=/distributions", "-e", "using Distributions; println(\"Distributions OK\")"]
