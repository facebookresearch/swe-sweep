# Maximally-buggy gorm — frozen at anchor version v1.23.5.
#
# Built upstream by `pandora construct build-image -t gorm@v1.23.5`, which prepares the build context
# from the local clone (no GitHub access — see docs/ai/010-design/005-style-conventions.md):
# it exports the source tree at v1.23.5 into ./gorm and copies this file in as ./Dockerfile.
# The image holds the tree with a `baseline` commit+tag; the host-controlled evaluator
# (tasks/gorm/task.yaml) does `git reset --hard baseline`, then applies the per-bug
# test/gold patches.
#
# Why v1.23.5: both patches apply for 27 subtasks here, against 26 at v1.23.3 (which is
# where the coverage curve peaks, 57 live), 25 at v1.23.9, 22 at v1.24.2 and 16 at v1.25.5.
# The 1.23 line is the plateau on both measures. See
# docs/ai/040-experiments/gorm/260820-anchor-choice.md.
#
# Why Go 1.18: both go.mod files declare `go 1.14`, and v1.23.5 is April 2022 — Go 1.18 is
# the period-correct toolchain and the last one before generics reshaped the standard
# library's build.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/go-gorm/gorm.git /src \
 && git -C /src checkout --quiet v1.23.5 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM golang:1.18-bullseye
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# git supports host-directed reset/apply, and gcc is required because the sqlite driver is cgo — `mattn/go-sqlite3`
# compiles the amalgamation, so CGO_ENABLED=1 needs a C toolchain present at *test* time,
# not only at image-build time.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends git ca-certificates python3 gcc libc6-dev; \
    ln -sf /usr/bin/python3 /usr/local/bin/python; \
    rm -rf /var/lib/apt/lists/*

COPY --from=swesweep-src /src /gorm
WORKDIR /gorm

# The census container has no network, so every module the two modules need has to be in the
# image's module cache already. `go mod download` is run once per module: the root one, and
# the integration suite in tests/, which is a *separate* module with its own go.mod (it
# `replace`s gorm.io/gorm with ../, so it always tests this tree).
RUN go mod download all
RUN cd tests && go mod download all

# Warm the build cache so the first census invocation is not also a cold compile of the
# sqlite amalgamation, which is the slowest single thing in this image.
RUN go build ./... && cd tests && go test -count=1 -run __warm_cache_no_such_test__ . || true

# Prove the suite is green *before* any patch is applied. A pristine failure reads as
# `fails_pre_gold` for every subtask and would quietly inflate the whole census. GORM_DIALECT
# is left unset on purpose: that is the sqlite path, the one the census runs.
RUN cd tests && go test -count=1 -run 'TestCount$' .

RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "gorm maxbug source" && git tag baseline

CMD ["go", "version"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
