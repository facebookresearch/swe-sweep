# Maximally-buggy mypy — frozen at anchor version 1.13.0.
#
# Built upstream by `pandora construct build-image -t mypy@1.13.0`, which prepares the build context
# from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the mypy source tree at v1.13.0
# into ./mypy and copies this file in as ./Dockerfile. The image holds the mypy git tree with
# a `baseline` commit+tag; the host-controlled evaluator (tasks/mypy/task.yaml) does
# `git reset --hard baseline`, then applies the per-bug test/gold patches.
#
# mypy is PURE PYTHON here: the wheels PyPI ships are mypyc-compiled, but the repo runs
# interpreted straight from the tree, which is how its own test suite runs it. So this image
# has no build step, `baseline` is the whole truth, and neither the reproduce nor the eval
# runner rebuilds anything after a patch (both pass needs_build=False).
#
# Why 1.13.0 and not the coverage peak: mypy is the case where the peak loses. 334 subtasks
# are live at v0.981 (Sept 2022, the peak) but only 53 of them still apply there, against 260
# live and 95 applying at v1.13.0 — see
# docs/ai/040-experiments/mypy/260818-anchor-choice.md. mypy rewrites its own checker often
# enough that a 2025 patch has nothing to attach to in a 2022 tree.
#
# There is no submodule to worry about: mypy vendors typeshed in-tree at mypy/typeshed, so
# the `git archive` export carries the stubs the checker needs at runtime.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/python/mypy.git /src \
 && git -C /src checkout --quiet v1.13.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM python:3.12-slim-bookworm
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# git is needed in-container to reset/apply/clean between instances. mypy links against no
# system library, so that is the whole list.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends git ca-certificates; \
    rm -rf /var/lib/apt/lists/*

# Runtime + test dependencies at the versions test-requirements.txt pins at this tag —
# mypy-requirements.txt plus the parts of the test pins the suite actually imports. The
# linters pinned there (black, ruff) are pre-commit's business, not the test suite's.
# lxml is left out: its pin at this tag excludes Python 3.12, and only the optional HTML
# report uses it.
RUN pip install --no-cache-dir \
        "typing_extensions==4.12.2" \
        "mypy_extensions==1.0.0" \
        "pytest==8.1.1" \
        "pytest-xdist==3.3.1" \
        "execnet==2.0.2" \
        "attrs==23.1.0" \
        "filelock==3.12.4" \
        "psutil==5.9.6" \
        "tomli==2.0.1" \
        "setuptools"

# mypy source tree at the anchor ref, exported from the local clone into the build context
# (see the header). It is imported straight from the working tree: the runners invoke pytest
# with cwd=/mypy, which puts /mypy on sys.path, so there is nothing to install and no build
# artifacts to keep in sync.
COPY --from=swesweep-src /src /mypy
WORKDIR /mypy

# Make the exported tree a git repo (the export carries no .git), commit the source and tag
# it `baseline`. With no compiled core there is no artifact/source split to manage — the
# tree is source all the way down, so an agent's extracted patch is clean by construction.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "mypy maxbug source" && git tag baseline

CMD ["python", "-c", "import mypy.version; print('mypy', mypy.version.__version__)"]
