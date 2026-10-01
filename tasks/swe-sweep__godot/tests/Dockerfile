# Maximally-buggy Godot — the focal-era candidates, 4.2-stable and 4.3-stable.
#
# Built upstream by `pandora construct build-image -t godot@<v>`, which prepares the build context
# under data/tasks/godot/maxbug/<v>/context/: it exports the Godot source tree at that tag
# FROM THE LOCAL CLONE (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md) into ./godot, and copies this file in as
# ./Dockerfile.
#
# One file for both candidates because the recipe is the same: upstream's own
# `linux_builds.yml` runs on `ubuntu-20.04` for 4.2 and 4.3 alike, so gcc 9 and that era's
# X11/Wayland headers are exactly the toolchain both trees were tested against. SCons
# comes from pip at the version the same workflow pins, not from apt, because focal's apt
# SCons is older than the SConstruct's floor. 4.4 moved to jammy and has its own file.
#
# Built at Meta through FwdProxy like every other maxbug image: `pandora construct
# build-image` wraps the build in `sudo with-proxy` and passes `--network=host` (rootless
# podman can't route to FwdProxy's IPv6 — see
# docs/ai/030-debug/260626-maxbug-image-registry-blocked.md). With FwdProxy in front of
# apt, apt's unprivileged `_apt` sandbox user cannot read the proxied download, so apt is
# told to run as root before it touches the network.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/godotengine/godot.git /src \
 && git -C /src checkout --quiet 4.3-stable \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM ubuntu:20.04
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

ENV DEBIAN_FRONTEND=noninteractive
RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    echo 'Acquire::Retries "5";' >> /etc/apt/apt.conf.d/10sandbox; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        build-essential pkg-config git ca-certificates python3 python3-pip \
        libx11-dev libxcursor-dev libxinerama-dev libxi-dev libxrandr-dev \
        libxkbcommon-dev libgl1-mesa-dev libglu1-mesa-dev \
        libasound2-dev libpulse-dev libudev-dev libdbus-1-dev \
        libwayland-dev libwayland-bin; \
    rm -rf /var/lib/apt/lists/*
# Acquire::Retries is not belt-and-braces: this apt runs through FwdProxy, which returns
# an occasional 502 on a single .deb, and one failed fetch fails the whole build minutes
# in. `libwayland-bin` is the one dependency upstream's workflow installs separately —
# it carries `wayland-scanner`, which the Wayland display driver's build shells out to.

# SCons at the version upstream's CI pins for 4.3 (.github/actions/godot-deps).
RUN python3 -m pip install --no-cache-dir "scons==4.8.0" \
    && ln -sf /usr/bin/python3 /usr/local/bin/python

# Godot source tree at the candidate ref, exported from the local clone into the build
# context (see the header). Godot vendors everything it needs under `thirdparty/` and has
# no submodules, so this tree is complete and the build needs no further downloads.
#
# `libfontconfig` is deliberately absent: Godot dlopen's it and prints one "cannot open
# shared object file" line when it is missing, which is cosmetic — the whole suite passes
# clean without it.
COPY --from=swesweep-src /src /godot
WORKDIR /godot

# Make the exported tree a git repo (the export carries no .git), commit the source and
# tag it `baseline` — a SOURCE-ONLY tree, so an agent's extracted patch can never carry a
# build artifact.
#
# SCons has no out-of-source mode, so unlike the cmake-based images the build output DOES
# land in the tree: object files beside their sources, the binary in `bin/`, the generated
# headers as `*.gen.*`, and SCons' own `.sconsign.dblite`. All of those are covered by
# Godot's `.gitignore`, and the consumers reset with `git reset --hard baseline &&
# git clean -fdq` — no `-x` — so ignored files survive and every subtask's rebuild is
# incremental. Committing BEFORE the build is what keeps them out of `baseline`.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "godot maxbug source" && git tag baseline

# Godot resolves `user://` under the XDG dirs, and several tests write there (the Image
# round-trip, the PCK packer). A bare base image has no `/root/.cache`, and 4.2 does not
# create it — the write fails, the failure cascades, and the run ABORTS partway with the
# suite half-reported. 4.3 and 4.4 create it themselves; making it here costs nothing and
# is what keeps the pristine run clean at every candidate.
RUN mkdir -p /root/.cache /root/.config/godot /root/.local/share/godot

# The build the benchmark grades against, with upstream's own test flags:
#
#   tests=yes            links the doctest cases into the binary; without it `--test`
#                        aborts with "compiled without support for unit tests".
#   dev_build=yes        what upstream's CI uses for its unit-test jobs — it defines
#                        DEV_ENABLED, which several tests assert against.
#   debug_symbols=no     a dev_build carries ~2 GB of DWARF and the link is the slow part
#                        of every per-subtask rebuild. The tests read outcomes, not
#                        backtraces, so the symbols buy nothing here.
#   module_text_server_fb_enabled=yes   the fallback text server, which upstream's CI
#                        enables globally so the text-shaping cases have a server to run
#                        against.
#
# `werror=yes` from upstream's SCONSFLAGS is deliberately NOT set: a warning introduced by
# a patch under test must not turn into a build failure.
RUN scons platform=linuxbsd target=editor \
        tests=yes dev_build=yes debug_symbols=no \
        module_text_server_fb_enabled=yes \
        -j "$(nproc)"

# The unit tests are the doctest cases inside the editor binary. `--test` is consumed by
# `Main::test_entrypoint` before any of the engine's own argument parsing runs, and every
# remaining argument is handed to `doctest::Context` — which is what lets the runner add
# `--test-case=`, `--reporters=junit` and `--out=`. Display is a mock server registered by
# the test harness, so no X server and no `--headless` are needed.
CMD ["/godot/bin/godot.linuxbsd.editor.dev.x86_64", "--test", "--list-test-cases"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
