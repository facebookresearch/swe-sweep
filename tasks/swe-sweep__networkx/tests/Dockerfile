# Maximally-buggy networkx — frozen at anchor version networkx-2.8.
#
# Built upstream by `pandora construct build-image -t networkx@2.8`, which prepares the build
# context under data/networkx/maxbug/2.8/context/: it exports the networkx source tree at
# networkx-2.8 FROM THE LOCAL CLONE (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md) into ./networkx, and copies this file in
# as ./Dockerfile. The image holds the networkx git tree with a `baseline` commit+tag; the
# host-controlled evaluator (tasks/networkx/task.yaml) does
# `git reset --hard baseline`, then applies the per-bug test/gold patches.
#
# networkx is PURE PYTHON: no compiled core, so this image has no build step, `baseline` is
# the whole truth, and neither the reproduce nor the eval runner rebuilds anything after a
# patch (both pass needs_build=False).
#
# Why 2.8: networkx's crawled bug population is densest over 2022-2023, and
# networkx-2.8 (Apr 2022) sits at the head of that run.
#
# Built at Meta through FwdProxy like every other task image: `pandora construct
# build-image local` wraps the build in `sudo with-proxy` with `--network=host`, so the
# FROM pull and the pip fetch below reach the network through the proxy.
# NOTE the base is the FULL python image, not `-slim`. The runners need `git` inside the
# container, and on this infra apt cannot get it: `deb.debian.org` is unreachable through
# FwdProxy, and the archive.debian.org rewrite the older images use only carries EOL
# suites, which bookworm is not. The non-slim images are built on buildpack-deps and
# already ship git, so the whole apt step goes away. Costs image size, buys a build that
# works without a Debian mirror at all.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/networkx/networkx.git /src \
 && git -C /src checkout --quiet networkx-2.8 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM python:3.10-bookworm
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# Runtime + test dependencies, pinned to the networkx-2.8 era.
# networkx has NO required runtime dependencies, so this is the test tooling only.
RUN pip install --no-cache-dir "pytest==7.1.2"

# networkx source tree at the anchor ref, exported from the local clone into the build
# context (see the header). It is imported straight from the working tree: the runners
# invoke pytest with cwd=/networkx, which puts /networkx on sys.path, so there is nothing to
# install and no build artifacts to keep in sync.
COPY --from=swesweep-src /src /networkx
WORKDIR /networkx

# Make the exported tree a git repo (the export carries no .git), commit the source and
# tag it `baseline`. With no compiled core there is no artifact/source split to manage —
# the tree is source all the way down, so an agent's extracted patch is clean by
# construction.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "networkx maxbug source" && git tag baseline

CMD ["python", "-c", "import networkx; print('networkx', networkx.__version__)"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
