# Maximally-buggy ModelingToolkit.jl — frozen at anchor version v9.33.0.
#
# Built upstream by `pandora construct build-image -t modelingtoolkit-jl@9.33.0`, which prepares the
# build context under data/modelingtoolkit-jl/maxbug/9.33.0/context/: it exports the source
# tree at v9.33.0 FROM THE LOCAL CLONE (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md) into ./modelingtoolkit, and copies this file
# in as ./Dockerfile. The image holds the git tree with a `baseline` commit+tag; the runner
# does `git reset --hard baseline`, then applies the per-bug test/gold patches.
#
# Why 9.33.0 (Aug 2024): the coverage curve peaks at 53 live subtasks in Jan 2026, but that
# peak sits inside the monorepo era, where the suite is driven by SciMLTesting across
# sub-package environments. v9.33.0 carries 52 — a tie within noise — on the flat mid-2024
# plateau, where `runtests.jl` is a plain list of `@safetestset` includes against a single
# environment. See docs/ai/040-experiments/modelingtoolkit-jl/.
#
# Why Julia 1.10: period-correct for an Aug-2024 release (1.10 was the LTS the repo's CI
# ran on) and above the `julia = "1.9"` floor its Project.toml declares.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/SciML/ModelingToolkit.jl.git /src \
 && git -C /src checkout --quiet v9.33.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM docker.io/library/julia:1.10-bookworm
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# git supports host-directed reset/apply. gcc is a *test* dependency here: `ccompile.jl`
# compiles a generated C function and the suite says so out loud. Python remains available
# for repository tooling. With FwdProxy in front of apt, apt's unprivileged `_apt` sandbox
# user can't read the proxied download, so let apt run as root first.
RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    apt-get update; \
    apt-get install -y --no-install-recommends git ca-certificates gcc g++ python3 python-is-python3; \
    rm -rf /var/lib/apt/lists/*

# Source tree at the anchor ref, exported from the local clone into the build context.
COPY --from=swesweep-src /src /modelingtoolkit
WORKDIR /modelingtoolkit

# Make the exported tree a git repo (the export carries no .git), commit the source and tag
# it `baseline`. Julia compiles on load and writes nothing into the source tree, so the tree
# is source all the way down and an extracted patch is clean by construction.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "modelingtoolkit maxbug source" && git tag baseline

# A depot inside the image, so the dependency downloads and precompile caches are baked in
# rather than re-fetched per subtask — the reproduce container runs with `--network=none`.
ENV JULIA_DEPOT_PATH=/depot

# Pre-warm: resolve, download and precompile the *test* environment — the deps plus the
# `[targets] test` extras, which for this package means the whole SciML solver stack
# (OrdinaryDiffEq, Sundials, NonlinearSolve, Optimization, Ipopt) and is by far the largest
# thing the image carries.
#
# The suite is deliberately *not* run: `runtests.jl` is emptied for the duration, so
# `Pkg.test()` does its resolve/instantiate/precompile work and then exits. Running it here
# would be both wrong (this is the maximally-buggy commit, so red tests are the expected
# state) and far too slow — the full suite is hours. `git checkout` puts the real
# `runtests.jl` back, leaving the tree identical to `baseline`.
RUN set -eux; \
    echo 'nothing' > test/runtests.jl; \
    julia -e 'using Pkg; Pkg.activate("/modelingtoolkit"); Pkg.instantiate(); Pkg.test()'; \
    git checkout -- test/runtests.jl; \
    git diff --quiet

# The actual build gate: the package must load and the environment must be complete. A
# missing test-only dependency would otherwise only surface per-subtask, as a load error.
RUN julia --project=/modelingtoolkit -e 'using ModelingToolkit; println("ModelingToolkit loads OK")' \
    && julia --project=/modelingtoolkit -e 'using Pkg; Pkg.status()'

# Offline from here on: the reproduce/eval containers get `--network=none`, so Pkg must
# resolve purely from what the pre-warm installed. Set after the pre-warm on purpose —
# earlier it would have blocked the downloads above.
ENV JULIA_PKG_OFFLINE=true

CMD ["julia", "--project=/modelingtoolkit", "-e", "using ModelingToolkit; println(\"ModelingToolkit OK\")"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
