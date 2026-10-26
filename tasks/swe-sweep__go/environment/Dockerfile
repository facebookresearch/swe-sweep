# Maximally-buggy Go — frozen at the go1.17.5 tag (2021-12-09).
#
# Built upstream by `pandora construct build-image -t go@go1.17.5`, which prepares the build context
# from the local clone (no GitHub access — see docs/ai/010-design/005-style-conventions.md):
# it exports the Go source tree at that tag into ./go and copies this file in as
# ./Dockerfile. The image holds the tree with a `baseline` commit+tag; the host-controlled
# evaluator (tasks/go/task.yaml) does `git reset --hard baseline`, applies the
# per-bug test/gold patches, and runs `go test`.
#
# Why go1.17.5: Go's coverage curve is flat and peaks in 2017 (1,081 live subtasks at
# go1.8.2 against 805 here), but the 2016-2017 tags carry TLS test certificates that have
# since expired and a C-era `go1.4` bootstrap, and neither survives contact with a modern
# host. go1.17.5 is the best point of the era that still builds and still runs green.
#
# Three things are specific to a Go task:
#
# 1. **The image's own `bin/go` is the toolchain, and that is the whole point.** `make.bash`
#    builds the frozen tree with a bootstrap Go and installs the result into /go/bin, so
#    `GOROOT` is the anchor itself. Running the system Go instead would compile the
#    *system's* standard library and grade nothing. Everything downstream — the `go` suite
#    in task.yaml, the census, the eval gate — depends on PATH resolving to /go/bin/go.
#
# 2. **There is no per-subtask build.** `go test` recompiles every package a patch changed
#    straight from source, standard library and runtime included, keyed on content in the
#    build cache. So `needs_build: false`, and a subtask costs one `go test`.
#
# 3. **`git init` happens before `make.bash`.** Go's own .gitignore covers /bin/, /pkg/ and
#    the generated z*.go files, so committing the pristine tree first leaves everything the
#    build produces untracked-and-ignored — which is exactly what survives the runner's
#    `git reset --hard baseline` + `git clean -fdq` between subtasks.

# The bootstrap toolchain, and nothing else from this image. Go 1.17 needs a Go 1.4-or-later
# bootstrap; using the matching released minor keeps the two compilers in the same language
# era, so `cmd/dist` cannot trip over a construct its bootstrap does not know.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/golang/go.git /src \
 && git -C /src checkout --quiet go1.17.5 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM golang:1.17-bullseye AS bootstrap

FROM debian:bullseye
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

ENV DEBIAN_FRONTEND=noninteractive
# `gcc`/`libc6-dev` are for cgo — a large part of net, os/user and crypto builds against it,
# and without a C toolchain those packages silently switch to their pure-Go implementations
# and test something else. `python3` is the container-session interpreter the runner uses.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        git ca-certificates gcc libc6-dev python3 tzdata; \
    ln -sf /usr/bin/python3 /usr/local/bin/python; \
    rm -rf /var/lib/apt/lists/*

COPY --from=bootstrap /usr/local/go /usr/local/go-bootstrap
ENV GOROOT_BOOTSTRAP=/usr/local/go-bootstrap

# Go source tree at the anchor tag, exported from the local clone into the build context
# (see the header).
COPY --from=swesweep-src /src /go

# A release tarball carries a VERSION file; a git tag does not. Without it `cmd/dist` has to
# reconstruct the version from git history, and the fresh repository created below has no
# release tag to find. Writing it makes `go version` say go1.17.5 and takes git off the
# build's critical path.
RUN printf 'go1.17.5' > /go/VERSION

WORKDIR /go

# Make the exported tree a git repo (the export carries no .git), commit the pristine source
# and tag it `baseline`. Before the build, so the build's output stays ignored — see the
# header.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "go maxbug source" && git tag baseline

WORKDIR /go/src
RUN ./make.bash

ENV GOROOT=/go
ENV PATH=/go/bin:$PATH
# The census container has no network. Go's standard library has no external dependency and
# `src/cmd` vendors its own, so nothing needs fetching — `off` turns a would-be hang into an
# immediate error.
ENV GOPROXY=off
# `go test` writes here; keeping it out of /go means `git clean` never touches it.
ENV GOCACHE=/root/.cache/go-build GOPATH=/root/go

# Prove the suite is green *before* any patch is applied. A pristine failure reads as
# `fails_pre_gold` for every subtask and would quietly inflate the whole census. `strings`
# is pure Go and hermetic; `net/http` exercises the cgo/network half that most often breaks
# on a host the tree has never seen.
RUN go version \
    && go test -count=1 -run 'TestSplit$' strings \
    && go test -count=1 -run 'TestServerTimeouts$' net/http

CMD ["go", "version"]
