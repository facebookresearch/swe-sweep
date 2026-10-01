# Maximally-buggy echo — frozen at anchor version v4.2.1.
#
# Built upstream by `pandora construct build-image -t echo@v4.2.1`, which prepares the build context
# from the local clone (no GitHub access — see docs/ai/010-design/005-style-conventions.md):
# it exports the source tree at v4.2.1 into ./echo and copies this file in as ./Dockerfile.
# The image holds the tree with a `baseline` commit+tag; the host-controlled evaluator
# (tasks/echo/task.yaml) does `git reset --hard baseline`, then applies the per-bug
# test/gold patches.
#
# Why v4.2.1: it ties for the top of the coverage curve (20 live subtasks) and has the best
# host-side apply rate — 21 test patches and 13 gold+test pairs apply here, against 10 at
# v4.1.16. See docs/ai/040-experiments/echo/260820-anchor-choice.md.
#
# Why Go 1.16: go.mod declares `go 1.15` and the tag is March 2021, so 1.16 is the
# period-correct toolchain — the first release where modules are on by default, which is
# how this tree expects to be built.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/labstack/echo.git /src \
 && git -C /src checkout --quiet v4.2.1 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM golang:1.16-bullseye
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# git supports host-directed reset/apply. echo is pure Go with no cgo.
RUN set -eux; \
    sed -i '\|^deb http://security.debian.org|d' /etc/apt/sources.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends git ca-certificates python3; \
    ln -sf /usr/bin/python3 /usr/local/bin/python; \
    rm -rf /var/lib/apt/lists/*

COPY --from=swesweep-src /src /echo
WORKDIR /echo

# The census container has no network, so every module the tree needs has to be in the
# image's module cache already.
RUN go mod download all

# Warm the build cache so the first census invocation is not also a cold compile.
RUN go build ./... || true

# Prove the suite is green *before* any patch is applied. A pristine failure reads as
# `fails_pre_gold` for every subtask and would quietly inflate the whole census. The radix
# router is the densest part of the suite and the commonest patch target.
RUN go test -count=1 -run 'TestRouterStatic$' .

RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "echo maxbug source" && git tag baseline

CMD ["go", "version"]
