# Maximally-buggy conan — frozen at anchor version 2.4.1.
#
# Built upstream by `pandora construct build-image -t conan@2.4.1`, which prepares the build context
# from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the conan source tree at 2.4.1
# into ./conan and copies this file in as ./Dockerfile. The image holds the conan git tree
# with a `baseline` commit+tag; the host-controlled evaluator (tasks/conan/task.yaml)
# does `git reset --hard baseline`, then applies the per-bug test/gold patches.
#
# conan is PURE PYTHON: no compiled core, so this image has no build step and neither runner
# rebuilds anything after a patch (both pass needs_build=False).
#
# Why 2.4.1: conan's coverage peak (Jan 2023) sits just before the 2.0 rewrite, and a 2.x
# patch has nothing to attach to in a 1.x tree — 139 subtasks are live at 1.59.0 but only 15
# apply. 2.4.1 has 83 live and 37 applying, the best of the five candidates measured in
# docs/ai/040-experiments/conan/260818-anchor-choice.md.
#
# The suite is functional: many cases build real packages with a compiler, so build-essential
# and cmake are part of the image rather than optional extras.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/conan-io/conan.git /src \
 && git -C /src checkout --quiet 2.4.1 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM python:3.10-slim-bookworm
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        git ca-certificates build-essential cmake pkg-config; \
    rm -rf /var/lib/apt/lists/*

# Runtime + test dependencies, at the bounds conans/requirements.txt and
# requirements_dev.txt carry at this tag. `docker` is in the dev list for the handful of
# cases that drive a registry container; they cannot run here and are expected to skip.
RUN pip install --no-cache-dir \
        "requests>=2.25,<3.0.0" "urllib3>=1.26.6,<1.27" "colorama>=0.4.3,<0.5.0" \
        "PyYAML>=6.0,<7.0" "patch-ng>=1.17.4,<1.18" "fasteners>=0.15" \
        "distro>=1.4.0,<=1.8.0" "Jinja2>=3.0,<4.0.0" "python-dateutil>=2.8.0,<3" \
        "pytest>=7,<8.0.0" "pytest-xdist" "parameterized>=0.6.3" "mock>=1.3.0,<1.4.0" \
        "WebTest>=2.0.18,<2.1.0" "bottle" "PyJWT" "pluginbase" "setuptools"

COPY --from=swesweep-src /src /conan
WORKDIR /conan

# conan is imported from the working tree by its own suite (pytest runs with cwd=/conan), but
# the CLI entry point is what many functional cases invoke, so the package is also installed
# in editable mode — the tree stays the single source of truth after a patch.
RUN pip install --no-cache-dir -e .

RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "conan maxbug source" && git tag baseline

CMD ["conan", "--version"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
