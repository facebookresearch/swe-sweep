# Maximally-buggy mongoose — frozen at anchor version 6.6.2.
#
# Built upstream by `pandora construct build-image -t mongoose@6.6.2`, which prepares the build context
# from the local clone (no GitHub access — see docs/ai/010-design/005-style-conventions.md):
# it exports the mongoose source tree at 6.6.2 into ./mongoose and copies this file in as
# ./Dockerfile. The image holds the mongoose git tree with a `baseline` commit+tag; the
# host-controlled evaluator (tasks/mongoose/task.yaml) does `git reset --hard baseline`,
# then applies the per-bug test/gold patches.
#
# mongoose is PLAIN JAVASCRIPT: nothing is compiled, so this image has no build step and both
# runners pass needs_build=False — a patch is live the moment `git apply` returns.
#
# Why 6.6.2: mongoose's coverage peak (Sept 2022) is also its best anchor — 192 subtasks live
# and 64 still applying, against 42 at the far later 8.16.0. See
# docs/ai/040-experiments/mongoose/260818-anchor-choice.md.
#
# **A real mongod runs beside the tests.** Most of mongoose's suite talks to a database, and a
# mocked one would grade a different library: the tests connect to mongodb://127.0.0.1:27017.
# The runner starts mongod explicitly because host-controlled sessions replace this image's
# entrypoint with their own keepalive process. The entrypoint remains useful for direct runs.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/Automattic/mongoose.git /src \
 && git -C /src checkout --quiet 6.6.2 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM node:16-bullseye
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# MongoDB 6.0 for the era, from its own apt repo, plus git for the reset/apply cycle.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends git ca-certificates curl gnupg python3; \
    ln -sf /usr/bin/python3 /usr/local/bin/python; \
    curl -fsSL https://pgp.mongodb.com/server-6.0.asc \
        | gpg -o /usr/share/keyrings/mongodb-server-6.0.gpg --dearmor; \
    echo "deb [signed-by=/usr/share/keyrings/mongodb-server-6.0.gpg] https://repo.mongodb.org/apt/debian bullseye/mongodb-org/6.0 main" \
        > /etc/apt/sources.list.d/mongodb-org-6.0.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends mongodb-org-server; \
    rm -rf /var/lib/apt/lists/*; \
    mkdir -p /data/db

COPY --from=swesweep-src /src /mongoose
WORKDIR /mongoose

# The dependency tree at this tag. **mongoose gitignores its lockfile**, so there is nothing
# to install deterministically from and `npm ci` refuses outright — this is `npm install`,
# which resolves each dependency to the newest release inside the range package.json declares.
# The ranges are the period-correct part; the exact versions are not, and a dependency that
# breaks its own semver can therefore move this image under us. Dev dependencies are required
# — mocha itself is one.
RUN npm install --no-audit --no-fund

# mongod has to be up before any test runs — and this wrapper doubles as the escape from
# the node image's own entrypoint, which would otherwise prepend `node` to the host's
# repository command. It execs "$@" verbatim.
# It is started here as a background process by the image's entrypoint wrapper.
RUN printf '#!/bin/sh\nset -e\nmongod --fork --logpath /var/log/mongod.log --bind_ip 127.0.0.1\nexec "$@"\n' \
        > /usr/local/bin/with-mongod && chmod +x /usr/local/bin/with-mongod
ENTRYPOINT ["/usr/local/bin/with-mongod"]

RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "mongoose maxbug source" && git tag baseline

CMD ["node", "-e", "console.log('mongoose', require('/mongoose/package.json').version)"]
