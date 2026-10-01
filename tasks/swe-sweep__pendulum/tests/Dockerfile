# Maximally-buggy pendulum — frozen at candidate anchor version 2.0.5.
#
# Built upstream by `pandora construct build-image -t pendulum@2.0.5`, which prepares the build
# context under data/pendulum/maxbug/2.0.5/context/: it exports the pendulum source tree
# at tag 2.0.5 FROM THE LOCAL CLONE (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md) into ./pendulum, and copies this file in as
# ./Dockerfile.
#
# Why 2.0.5: pendulum's coverage curve peaks there (18 live subtasks, 2019-07), a clear
# top over the 2.0.x line.
#
# Why python 3.8: 2.0.5 declares `~2.7 || ^3.4` and its CI matrix stopped at 3.7, so a
# modern interpreter is out. 3.8 is the newest that still ships `distutils`, which
# `build.py` and the in-place extension build below both use, and pendulum's own code is
# 3.8-clean.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/sdispater/pendulum.git /src \
 && git -C /src checkout --quiet 2.0.5 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM docker.io/library/python:3.8-slim-bullseye
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# git is needed in-container to reset/apply/clean between subtasks; gcc builds the two C
# accelerators. With FwdProxy in front of apt, apt's unprivileged `_apt` sandbox user
# cannot read the proxied download, so let apt run as root first.
RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    apt-get update; \
    apt-get install -y --no-install-recommends git ca-certificates gcc libc6-dev; \
    rm -rf /var/lib/apt/lists/*

# Runtime + test dependencies, pinned to the 2.0.5 era. pendulum is a poetry project with
# a `build.py`, so there is no setup.py to install from; the tree is a flat layout
# (`pendulum/` at the repo root) and the runners invoke pytest with cwd=/pendulum, which
# puts it on sys.path. pytest 4.6.11 is the last release that runs on this interpreter's
# era of the ecosystem and is what the other Python images here use.
RUN pip install --no-cache-dir \
        "python-dateutil==2.8.1" \
        "pytzdata==2019.3" \
        "pytz==2019.3" \
        "babel==2.7.0" \
        "pytest==4.6.11" \
        "setuptools<60"

# pendulum source tree at the candidate tag, exported from the local clone into the build
# context (see the header).
COPY --from=swesweep-src /src /pendulum
WORKDIR /pendulum

# Build the two C accelerators in place. pendulum falls back to a pure-Python
# implementation when they are missing, and its own CI runs both — but the `.c` files are
# graded product code (they are in `source_globs`), so the image has to be the compiled
# variant or a fix to one of them could never be measured. The declarative runner
# configuration reruns this same command after each patch.
RUN python -c "\
from distutils.core import setup, Extension; \
setup(script_args=['build_ext', '--inplace'], ext_modules=[ \
    Extension('pendulum._extensions._helpers', ['pendulum/_extensions/_helpers.c']), \
    Extension('pendulum.parsing._iso8601', ['pendulum/parsing/_iso8601.c'])])"

# Make the exported tree a git repo (the export carries no .git), commit the source and
# tag it `baseline`. The built `.so` files are NOT committed (pendulum's .gitignore covers
# them), so `git reset --hard baseline && git clean -fdq` (no -x) leaves them in place and
# a subtask that touches no C file needs no rebuild.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "pendulum maxbug source" && git tag baseline

ENV TZ=UTC

CMD ["python", "-c", "import pendulum; print('pendulum', pendulum.__version__, pendulum.parsing._iso8601.__file__)"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
