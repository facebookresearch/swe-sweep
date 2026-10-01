# Maximally-buggy pandas — frozen at anchor version v1.3.0.
#
# Built upstream by `pandora construct build-image -t pandas@1.3.0`, which prepares the build
# context under data/pandas/maxbug/1.3.0/context/: it exports the pandas source tree at
# v1.3.0 FROM THE LOCAL CLONE (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md) into ./pandas, and copies this file in as
# ./Dockerfile. The image holds the pandas git tree with a source-only `baseline`
# commit+tag; the host-controlled evaluator
# (tasks/pandas/task.yaml) does `git reset --hard
# baseline`, reuses the prebuilt (gitignored) extensions, then applies the per-bug
# test/gold patches.
#
# Why 1.3.0 (Jul 2021): pandas' crawled bug population is densest over 2020–2023, and
# v1.3.0 sits in the middle of that run. The candidate range stops before v2.1.0, which
# is where pandas switched to meson — the image flow here rebuilds the compiled core with
# `python setup.py build_ext --inplace`, which that switch removes.
#
# Built at Meta through FwdProxy exactly like every other task image: `pandora construct
# build-image local` wraps the build in `sudo with-proxy` and passes `--network=host`, so
# the FROM pull + the apt/pip fetches below reach the network through the proxy (sudo
# because rootless podman can't route to FwdProxy's IPv6; see
# docs/ai/030-debug/260626-maxbug-image-registry-blocked.md). With FwdProxy in front of
# apt, apt's unprivileged `_apt` sandbox user can't read the proxied download, so we let
# apt run as root before touching the network.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/pandas-dev/pandas.git /src \
 && git -C /src checkout --quiet v1.3.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM python:3.8-slim-buster
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# Point apt at the Debian archive (buster is EOL) and install the toolchain. git is
# needed in-container (reset/apply/clean between instances); gcc/g++ build pandas'
# Cython-generated C and its handful of C++ extensions. pandas links against no external
# numerical library, so there is no BLAS/Fortran here.
RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    printf 'deb http://archive.debian.org/debian buster main\n\
deb http://archive.debian.org/debian-security buster/updates main\n' \
        > /etc/apt/sources.list; \
    apt-get -o Acquire::Check-Valid-Until=false update; \
    apt-get install -y --no-install-recommends \
        git gcc g++ make ca-certificates; \
    rm -rf /var/lib/apt/lists/*

# Pin the build/test tooling to the v1.3.0 era (mid-2021), from the release's own
# environment.yml: numpy>=1.17.3, Cython>=0.29.21, python-dateutil, pytz. `hypothesis` is
# NOT optional — pandas/conftest.py imports it at module scope, so without it the entire
# suite fails to collect. pytest is held below 7 because 1.3-era pandas still uses
# `pytest.warns(None)`, which pytest 7 removed.
RUN pip install --no-cache-dir \
        "numpy==1.20.3" \
        "cython==0.29.24" \
        "python-dateutil==2.8.2" \
        "pytz==2021.1" \
        "hypothesis==6.14.0" \
        "pytest==6.2.4"

# pandas source tree at the anchor ref, exported from the local clone into the build
# context (see the header). PANDAS_BUILD_PARALLEL is the env var the HOST passes the job
# count in; the build itself reads it via the `-j` flag the runner appends, because
# pandas' plain-setuptools setup.py has its own --parallel argument and reads no env var.
ENV PANDAS_BUILD_PARALLEL=4
COPY --from=swesweep-src /src /pandas
WORKDIR /pandas

# Make the exported tree a git repo (the export carries no .git), commit the source and
# tag it `baseline` — a SOURCE-ONLY tree. Build artifacts (.so/.pyc/Cython-generated .c)
# are NOT committed, so pandas' .gitignore keeps them out of `git diff` and a plain
# `git add -A` never stages them — this is what keeps an agent's extracted patch free of
# binary blobs and of half a megabyte of generated C. The build_ext below leaves those
# artifacts in the tree; being gitignored they SURVIVE the consumers'
# `git reset --hard baseline && git clean -fdq` (no -x), so pandas stays importable with
# no rebuild. Only a source-changing patch (agent/gold) triggers a rebuild afterwards.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "pandas maxbug source" && git tag baseline
RUN python setup.py build_ext --inplace -j 4

CMD ["python", "-c", "import pandas; print('pandas', pandas.__version__)"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
