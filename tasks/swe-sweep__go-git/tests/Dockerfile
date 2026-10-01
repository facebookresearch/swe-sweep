# Maximally-buggy go-git — frozen at candidate anchor version v5.5.0.
#
# Built upstream by `pandora construct build-image -t go-git@v5.5.0`, which prepares the build
# context from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the source tree at v5.5.0 into
# ./go-git and copies this file in as ./Dockerfile. The image holds the tree with a
# `baseline` commit+tag; the host-controlled evaluator (tasks/go-git/task.yaml)
# does `git reset --hard baseline`, then applies the per-bug test/gold patches.
#
# Why v5.5.0: the SZZ coverage curve peaks at 63 live subtasks in 2023-01 and is flat
# either side of it; v5.5.0 is the earliest tag on that plateau (62 live).
#
# Why Go 1.19: the tag is 2022-11 and `go.mod` still declares `go 1.13`, but the
# dependency set it pins (golang.org/x/crypto v0.3.0, x/net v0.2.0) is the 2022-11
# generation and does not build on a 1.13 toolchain. 1.19 is the release current at the
# tag, so it is the period-correct choice.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/go-git/go-git.git /src \
 && git -C /src checkout --quiet v5.5.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM docker.io/library/golang:1.19-bullseye
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# `git` is not only for the host-directed reset/apply: go-git's `plumbing/transport/file`
# suite shells out to the real `git-upload-pack` and `git-receive-pack`, and the compat
# tests drive the `git` binary directly. Without it those packages fail before any patch
# is applied and every one of their subtasks reads as `fails_pre_gold`.
RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        git git-daemon-run ca-certificates openssh-client python3; \
    ln -sf /usr/bin/python3 /usr/local/bin/python; \
    rm -rf /var/lib/apt/lists/*

# go-git's own suite reads `user.name`/`user.email` when it makes commits through the real
# git binary, and refuses to run in a directory owned by another uid.
RUN git config --global user.email v@x \
    && git config --global user.name v \
    && git config --global init.defaultBranch master \
    && git config --global --add safe.directory '*'

COPY --from=swesweep-src /src /go-git
WORKDIR /go-git

# The census container has no network, so every module the tree needs — including the
# fixture repositories, which go-git ships as the separate `go-git-fixtures` *module*
# rather than as a submodule — has to be in the image's module cache already.
RUN go mod download all

# Warm the build cache so the first census invocation is an incremental recompile rather
# than a cold build of the whole module graph.
RUN go build ./... && go test -count=1 -run XXX_NONE ./... > /dev/null 2>&1 || true

# A reproduction run has no network (unlike this build, which goes through FwdProxy), so
# say so: the go tool must fail loudly on a module it does not already have, rather than
# hang until the runner's timeout and report the subtask as unmeasurable.
#
# **cgo stays on.** `github.com/pjbgf/sha1cd/cgo` is go-git's collision-detecting SHA-1 and
# is reached from `plumbing/hash`, which is imported by nearly every package in the tree —
# with `CGO_ENABLED=0` its build constraints exclude every file in the package and the
# build dies with "build constraints exclude all Go files", which the runner reports as a
# collection error for the whole suite.
#
# Set **before** the smoke test below, deliberately: the build then proves the suite runs
# under exactly the environment the census will use, instead of under the build's own
# networked one. Setting it afterwards is what hid the cgo failure on the first attempt.
ENV GOFLAGS=-mod=mod \
    GOPROXY=off \
    GOSUMDB=off

# Prove the suite is green *before* any patch is applied. A pristine failure reads as
# `fails_pre_gold` for every subtask in that package and would quietly inflate the census.
# `plumbing/format/config` is pure parsing with no fixtures, and `plumbing/object` is the
# densest patch target in the repo.
RUN go test -count=1 ./plumbing/format/config/... \
    && go test -count=1 -run 'TestSuite' ./plumbing/format/idxfile/...

RUN git init -q \
    && git add -A && git commit -q -m "go-git maxbug source" && git tag baseline

CMD ["go", "version"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
