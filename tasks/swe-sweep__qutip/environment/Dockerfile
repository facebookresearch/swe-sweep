# Maximally-buggy qutip — frozen at anchor version v4.6.0.
#
# Built upstream by `pandora construct build-image -t qutip@4.6.0`, which prepares the build
# context under data/qutip/maxbug/4.6.0/context/: it exports the qutip source tree at
# v4.6.0 FROM THE LOCAL CLONE (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md) into ./qutip, and copies this file in as
# ./Dockerfile. The image holds the qutip git tree with a source-only `baseline`
# commit+tag; the host-controlled evaluator (tasks/qutip/task.yaml) does
# `git reset --hard baseline`, reuses the prebuilt (gitignored) extensions, then applies
# the per-bug test/gold patches.
#
# qutip has a COMPILED CORE (Cython extensions under qutip/cy/), so the runners rebuild
# after a patch with the default `python setup.py build_ext --inplace`. The image runs
# that build once, so a subtask's rebuild only recompiles what its patch touched.
#
# Why 4.6.0: qutip's SZZ coverage curve peaks on 2021-03-27 at 38 live subtasks, and
# v4.6.0 (Apr 2021) is the release tag on that peak with 36 — the most of any tag.
#
# NOTE the base is the FULL python image, not `-slim`. The runners need `git` inside the
# container, and on this infra apt cannot get it: `deb.debian.org` is unreachable through
# FwdProxy and the archive.debian.org rewrite the older images use only carries EOL
# suites, which bullseye is not. The non-slim images are built on buildpack-deps and
# already ship git and a C toolchain, so the whole apt step goes away.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/qutip/qutip.git /src \
 && git -C /src checkout --quiet v4.6.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM python:3.9-bullseye
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# Build + runtime + test dependencies, pinned to the v4.6.0 era.
# numpy is pinned BELOW 1.20 because that is what this release's own pyproject.toml
# requires to build against ("numpy>=1.16.6,<1.20"): the Cython extensions embed the
# numpy C ABI they were compiled against, and a newer build-time numpy fails the runtime
# ABI check on every `import qutip`.
# cython stays installed at RUNTIME, not just for the build: qutip 4 compiles
# string-format Hamiltonians (the `runtime_compilation` extra) with it on the fly, and a
# fair number of solver tests take that path.
# pytest-rerunfailures is in the release's own `tests` extra, and the suite's
# `@pytest.mark.flaky` markers need it to be a known mark.
RUN pip install --no-cache-dir \
        "numpy==1.19.5" \
        "scipy==1.6.2" \
        "cython==0.29.23" \
        "setuptools<60" \
        "wheel<0.38" \
        "packaging==20.9" \
        "matplotlib==3.4.1" \
        "pytest==6.2.3" \
        "pytest-rerunfailures==9.1.1"

# qutip source tree at the anchor ref, exported from the local clone into the build
# context (see the header). It is imported straight from the working tree: the runners
# invoke pytest with cwd=/qutip, which puts /qutip on sys.path, so there is nothing to
# install — only the in-place extensions to build.
COPY --from=swesweep-src /src /qutip
WORKDIR /qutip

# Make the exported tree a git repo (the export carries no .git), commit the source and
# tag it `baseline` — a SOURCE-ONLY tree, which is why this runs BEFORE the build. Build
# artifacts (.so, the Cython-generated qutip/cy/*.c, the generated qutip/version.py) are
# all in qutip's own .gitignore, so a plain `git add -A` never stages them and an agent's
# extracted patch carries no binary blobs. Being gitignored they also SURVIVE the
# consumers' `git reset --hard baseline && git clean -fdq` (no -x), so qutip stays
# importable with no rebuild; only a source-changing patch triggers one.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "qutip maxbug source" && git tag baseline

# Build the Cython extensions in place, once, so a subtask's rebuild is incremental.
# This also writes the gitignored qutip/version.py that `import qutip` needs.
RUN python setup.py build_ext --inplace

CMD ["python", "-c", "import qutip; print('qutip', qutip.__version__)"]
