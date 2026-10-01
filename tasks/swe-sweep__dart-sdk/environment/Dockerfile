# Maximally-buggy Dart SDK — frozen at the `2.19.6` tag (2023-03-28), the newest stable tag
# on the coverage curve's plateau (see
# docs/ai/040-experiments/dart-sdk/260822-seed-and-curve.md: the plateau's stable tags all
# sit within 4% of each other, so the anchor is chosen on build cost, and newer is cheaper).
#
# Built upstream by `pandora construct build-image -t dart-sdk@2.19.6`, which prepares the build
# context from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the Dart source tree at that tag
# into ./dart-sdk and copies this file in as ./Dockerfile. The image holds the tree with a
# `baseline` commit+tag; the host-controlled evaluator (tasks/dart-sdk/task.yaml)
# does `git reset --hard baseline`, applies the per-bug test/gold patches, and rebuilds.
#
# Four things are specific to a Dart SDK task:
#
# 1. **The exported tree is only half a checkout.** Dart's dependencies are not git
#    submodules; they are listed in `DEPS` and fetched by `gclient`, Chromium's checkout
#    tool. Without them there is no `package:test`, no `.dart_tool/package_config.json` and
#    no `buildtools/` (gn, ninja, clang), so nothing resolves and nothing builds. The
#    `.gclient` written below names the already-exported tree as an **unmanaged** solution,
#    which is what stops gclient trying to re-clone the repository over it.
#
# 2. **depot_tools is pinned to the anchor's era.** It is a rolling checkout with no
#    releases, and today's gclient does not read a 2023 `DEPS` reliably. Checking out the
#    last commit before the anchor's date is the closest thing to a version pin it has.
#
# 3. **`baseline` is committed *before* gclient runs, and the excludes are written after.**
#    The runner does `git reset --hard baseline && git clean -fdq` between subtasks, so
#    everything gclient writes has to be both untracked and ignored or it is deleted after
#    the first bug. Dart's own .gitignore covers `/buildtools`, `/out` and
#    `/.dart_tool/package_config.json` but **not** `third_party/pkg`, whose own .gitignore
#    explicitly un-ignores it. The extra rules go in `.git/info/exclude`, which is not part
#    of the tree — so the frozen source stays exactly as released — and they must be written
#    after the baseline commit, or the tracked `third_party/` entries never get committed.
#
# 4. **Only a `runtime/` fix pays for a rebuild.** The analyzer, the CFE and dart2js are
#    Dart source that the built SDK runs directly, so a fix under `pkg/` needs no ninja at
#    all. That asymmetry is what makes this repository affordable.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/dart-lang/sdk.git /src \
 && git -C /src checkout --quiet 2.19.6 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM debian:bookworm
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

ENV DEBIAN_FRONTEND=noninteractive
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        git curl ca-certificates python3 python3-venv xz-utils unzip zip file \
        build-essential pkg-config lsb-release \
        python3-httplib2 python3-six python3-setuptools python3-pkg-resources; \
    rm -rf /var/lib/apt/lists/*

# depot_tools at the anchor's era (see the header). Cloned with history so the date-based
# checkout is possible; `DEPOT_TOOLS_UPDATE=0` is what stops it rolling itself forward again
# on the first gclient invocation, which would undo the pin.
RUN git clone -q https://chromium.googlesource.com/chromium/tools/depot_tools.git /depot_tools \
    && git -C /depot_tools checkout -q "$(git -C /depot_tools rev-list -1 --before=2023-04-01 HEAD)"
# `VPYTHON_BYPASS` makes depot_tools run on the system interpreter instead of fetching its
# own managed one through cipd — deterministic, and one less network dependency. The price
# is that the modules vpython would have provided have to come from apt above: without
# `python3-httplib2` gclient dies on its first import.
ENV PATH=/depot_tools:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    DEPOT_TOOLS_UPDATE=0 \
    DEPOT_TOOLS_METRICS=0 \
    VPYTHON_BYPASS="manually managed python not supported by chrome operations"

# Dart source tree at the anchor tag, exported from the local clone into the build context.
COPY --from=swesweep-src /src /dart/sdk
WORKDIR /dart/sdk

RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "dart-sdk maxbug source" && git tag baseline

# After the baseline commit (see the header): everything gclient is about to write must be
# untracked *and* ignored, or `git clean -fdq` deletes it between subtasks.
RUN printf '%s\n' \
      'third_party/' \
      'buildtools/' \
      'out/' \
      '.dart_tool/' \
      '.gclient_entries' \
      '.cipd/' \
    >> .git/info/exclude

WORKDIR /dart
RUN printf '%s\n' \
      'solutions = [{' \
      '  "name": "sdk",' \
      '  "url": "https://dart.googlesource.com/sdk.git",' \
      '  "deps_file": "DEPS",' \
      '  "managed": False,' \
      '  "custom_deps": {},' \
      '}]' \
    > /dart/.gclient

# One sync: the DEPS-listed packages into third_party/, then the hooks that fetch gn, ninja
# and clang from Google Storage and generate .dart_tool/package_config.json.
RUN gclient sync --no-history --shallow -D

WORKDIR /dart/sdk
RUN ./tools/build.py --mode release --arch x64 create_sdk

CMD ["/dart/sdk/out/ReleaseX64/dart-sdk/bin/dart", "--version"]
