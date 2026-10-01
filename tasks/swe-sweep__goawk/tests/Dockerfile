# Maximally-buggy goawk — frozen at candidate anchor version v1.23.2.
#
# Built upstream by `pandora construct build-image -t goawk@v1.23.2`, which prepares the build
# context from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the source tree at v1.23.2 into
# ./goawk and copies this file in as ./Dockerfile. The image holds the tree with a
# `baseline` commit+tag; the host-controlled evaluator (tasks/goawk/task.yaml)
# does `git reset --hard baseline`, then applies the per-bug test/gold patches.
#
# Why v1.23.2: the newest tag still within two of the peak (15 live subtasks), and the far
# end of the plateau. See docs/ai/040-experiments/goawk/.
#
# Why Go 1.20 rather than the `go 1.14` in go.mod: goawk vendors nothing (its go.mod has
# no requirements at all), so the toolchain is the only moving part, and 1.14 is too old
# for the Go 1.18 native fuzz tests the tree at this tag already contains. 1.20 is the
# newest toolchain that predates the Go 1.22 loop-variable change, so the semantics a
# `go 1.14` module gets here are the ones the tree was written against.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/benhoyt/goawk.git /src \
 && git -C /src checkout --quiet v1.23.2 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM docker.io/library/golang:1.20-bullseye
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# gawk is not optional: goawk's root-package suite is *differential*. TestAWK and TestGAWK
# execute the real awk on every program under testdata/ and compare its output byte for
# byte with goawk's, so without it every root-package subtask reports a pristine failure.
# `git` supports the host-directed reset/apply.
RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        git ca-certificates gawk locales python3 python-is-python3; \
    sed -i 's/^# *en_US.UTF-8/en_US.UTF-8/' /etc/locale.gen; \
    locale-gen; \
    rm -rf /var/lib/apt/lists/*
# The Python alias is retained only for repository-owned tooling; benchmark control runs on the host.

# goawk source tree at the candidate ref, exported from the local clone into the build
# context (see the header).
COPY --from=swesweep-src /src /goawk
WORKDIR /goawk

# The differential tests are locale-sensitive: gawk's idea of a character follows LC_ALL,
# goawk's does not. The interpreter suite drives gawk with a multi-byte record separator
# (`BEGIN { RS="ö" }`) and compares the split byte for byte, so the locale has to be a
# real UTF-8 one — a generated `en_US.UTF-8`, which is what goawk's own CI runs under.
# Neither `C` nor `C.UTF-8` works: under both, `gawk --posix` splits the separator
# byte-by-byte and the case reports a spurious mismatch.
#
# `GOFLAGS=-mod=mod` keeps a tree written before Go 1.16 building the way it expects, and
# `GOPROXY=off` makes a stray new dependency fail loudly rather than hang until the
# runner's timeout: the census container has no network. goawk itself needs none.
ENV LC_ALL=en_US.UTF-8 \
    LANG=en_US.UTF-8 \
    CGO_ENABLED=0 \
    GOFLAGS=-mod=mod \
    GOPROXY=off

# Make the exported tree a git repo (the export carries no .git) and tag it `baseline`.
# This happens *before* the pre-flight below, because the root-package suite rewrites
# testdata/output/* as it runs (TestAWK's `-writegoawk` flag defaults to true). Tagging
# first means the baseline is the pristine tag, so a subtask's recorded test patch still
# applies to it; the `git reset --hard baseline` at the end undoes the rewrites.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "goawk maxbug source" && git tag baseline

# Warm the build cache so a subtask's rebuild is incremental rather than a cold compile.
# There are no modules to download, so compiling every test binary is the whole warm-up.
RUN go build ./... && go vet ./... > /dev/null 2>&1 || true
RUN go test -count=1 -run 'XXX_NO_SUCH_TEST' ./... > /dev/null

# Prove the suite is green *before* any patch is applied. A pristine failure reads as
# `fails_pre_gold` for every subtask and would quietly inflate the whole census.
#
# Both halves are checked, because both are patch targets: `interp` holds 25 of the 42
# accepted subtasks' tests and the root package — the differential one that needs gawk —
# holds 17. The root package is the risky one, so it is run in full.
RUN go test -count=1 ./interp/ ./lexer/ ./parser/
RUN go test -count=1 .

# Undo the pre-flight's writes to testdata/output/ and drop the built `goawk` binary, so
# the image ships a tree identical to the baseline commit.
RUN git reset --hard -q baseline && git clean -fdq

CMD ["go", "version"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
