# Maximally-buggy dateutil — frozen at anchor version 2.6.0.
#
# Built upstream by `pandora construct build-image -t dateutil@2.6.0`, which prepares the build
# context under data/dateutil/maxbug/2.6.0/context/: it exports the dateutil source tree at
# 2.6.0 FROM THE LOCAL CLONE (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md) into ./dateutil, and copies this file in
# as ./Dockerfile. The image holds the dateutil git tree with a `baseline` commit+tag; the
# host-controlled evaluator (tasks/dateutil/task.yaml) does
# `git reset --hard baseline`, then applies the per-bug test/gold patches.
#
# dateutil is PURE PYTHON: no compiled core, so this image has no build step, `baseline` is
# the whole truth, and neither the reproduce nor the eval runner rebuilds anything after a
# patch (both pass needs_build=False).
#
# Why 2.6.0: the earlier anchor candidate (Nov 2016), just ahead of dateutil's
# densest crawled-bug years (2017-2018).
#
# Built at Meta through FwdProxy like every other task image: `pandora construct
# build-image local` wraps the build in `sudo with-proxy` with `--network=host`, so the
# FROM pull and the pip fetch below reach the network through the proxy.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/dateutil/dateutil.git /src \
 && git -C /src checkout --quiet 2.6.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM python:3.6-slim-stretch
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# Point apt at the Debian archive (stretch is EOL) and install git — needed in-container
# to reset/apply/clean between instances. That is the whole system dependency list:
# dateutil links against nothing. With FwdProxy in front of apt, apt's unprivileged `_apt`
# sandbox user can't read the proxied download, so let apt run as root first.
RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    printf 'deb http://archive.debian.org/debian stretch main\n\
deb http://archive.debian.org/debian-security stretch/updates main\n' \
        > /etc/apt/sources.list; \
    apt-get -o Acquire::Check-Valid-Until=false update; \
    apt-get install -y --no-install-recommends git ca-certificates; \
    rm -rf /var/lib/apt/lists/*

# Runtime + test dependencies, pinned to the 2.6.0 era.
# dateutil's only runtime dependency is six; hypothesis is a real test dependency (its parser suite is property-based).
RUN pip install --no-cache-dir "six==1.10.0" "pytest==3.0.7" "hypothesis==3.6.1"

# dateutil source tree at the anchor ref, exported from the local clone into the build
# context (see the header). It is imported straight from the working tree: the runners
# invoke pytest with cwd=/dateutil, which puts /dateutil on sys.path, so there is nothing to
# install and no build artifacts to keep in sync.
COPY --from=swesweep-src /src /dateutil
WORKDIR /dateutil

# Make the exported tree a git repo (the export carries no .git), commit the source and
# tag it `baseline`. With no compiled core there is no artifact/source split to manage —
# the tree is source all the way down, so an agent's extracted patch is clean by
# construction.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "dateutil maxbug source" && git tag baseline

CMD ["python", "-c", "import dateutil; print('dateutil', dateutil.__version__)"]
