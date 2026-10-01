# Maximally-buggy terser — frozen at anchor version v5.8.0.
#
# Built upstream by `pandora construct build-image -t terser@v5.8.0`, which prepares the build
# context from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the terser source tree at v5.8.0
# into ./terser and copies this file in as ./Dockerfile. The image holds the terser git tree
# with a `baseline` commit+tag; the host-controlled evaluator
# (tasks/terser/task.yaml) does `git reset --hard baseline`, then applies the
# per-bug test/gold patches.
#
# There is NO transpile step. terser is ES modules and the tests import `../main.js`
# directly; `dist/` is only what npm publishes. So a gold patch is live the moment it
# applies and the runner passes needs_build=False.
#
# The runner-up candidate. v5.8.0 (Sep 2021) carries 16 live subtasks against v5.7.2's 18 —
# close enough that only the census can separate them, which is why both are built.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/terser/terser.git /src \
 && git -C /src checkout --quiet v5.8.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM node:16-bullseye-slim
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# git supports the host-directed reset/apply between instances. terser links against no
# system library, so that is the whole list.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends git ca-certificates; \
    rm -rf /var/lib/apt/lists/*

# terser source tree at the anchor ref, exported from the local clone into the build context
# (see the header).
COPY --from=swesweep-src /src /terser
WORKDIR /terser

# `npm ci` installs exactly the package-lock.json the tag committed, which is what keeps the
# image period-correct: `npm install` would re-resolve every caret range against today's
# registry and quietly change what the tests observe.
RUN npm ci --no-audit --no-fund

# Make the exported tree a git repo (the export carries no .git), commit the source and tag
# it `baseline`. node_modules/ is gitignored by the tree's own .gitignore, so the install
# stays out of the baseline commit and survives the runner's `git clean -fdq` (which is
# deliberately not `-fdx`).
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "terser maxbug source" && git tag baseline

# Prove the suite is green before any patch is applied: a pristine failure reads as
# fails_pre_gold and quietly inflates the census with subtasks that reproduce nothing. Both
# halves are checked — one corpus file through terser's own driver (which is what nearly
# every subtask runs through, and which exits non-zero on any failure) and the mocha suite.
RUN node test/compress.js collapse_vars.js \
    && node_modules/.bin/mocha test/mocha/minify.js

CMD ["node", "-e", "import('./main.js').then(m => console.log('terser ok', typeof m.minify))"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
