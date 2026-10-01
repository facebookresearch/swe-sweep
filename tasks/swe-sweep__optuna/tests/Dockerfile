# Maximally-buggy optuna — frozen at anchor version v2.5.0.
#
# Built upstream by `pandora construct build-image -t optuna@v2.5.0`, which prepares the build
# context from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the source tree at v2.5.0 into
# ./optuna and copies this file in as ./Dockerfile. The image holds the tree with a
# `baseline` commit+tag; the host-controlled evaluator (tasks/optuna/task.yaml) does
# `git reset --hard baseline`, then applies the per-bug test/gold patches.
#
# optuna is PURE PYTHON: no build step, `baseline` is the whole truth, and the runner passes
# needs_build=False.
#
# Why v2.5.0: the best host-side apply rate of the three best-covered tags — 34 test patches
# and 16 gold+test pairs, against 13 at v2.8.0 and 10 at v2.9.0 — on a curve whose peak is
# flat at ~35 live across that whole stretch.
#
# **The testing extra is not installable, on purpose.** optuna lists every framework it
# integrates with (tensorflow, torch, mxnet, chainer, lightgbm, mlflow, mpi4py …) as a test
# dependency. Installing that set would take longer than the census and pin the image to a
# GPU-less approximation of it anyway. What is installed is the core plus the handful the
# *non*-integration tests import; a subtask whose test lives under `tests/integration_tests/`
# reports no targets rather than a verdict.
#
# Why Python 3.8: v2.5.0 is February 2021.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/optuna/optuna.git /src \
 && git -C /src checkout --quiet v2.5.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM python:3.8-slim-bullseye
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends git ca-certificates; \
    rm -rf /var/lib/apt/lists/*

# The install_requires of this tag, plus the test dependencies the core suite imports.
#
# numpy is 1.22 rather than the tag's 1.20: optuna's own type hints use `numpy.typing.NDArray`,
# which only exists from 1.21, so the era-correct pin cannot even import the package. scipy
# moves with it.
RUN pip install --no-cache-dir \
        "alembic==1.5.4" \
        "cliff==3.6.0" \
        "cmaes==0.8.1" \
        "colorlog==4.7.2" \
        "joblib==1.0.1" \
        "numpy==1.22.4" \
        "packaging==20.9" \
        "scipy==1.8.1" \
        "sqlalchemy==1.3.23" \
        "tqdm==4.57.0" \
        "pytest==6.2.2" \
        "pandas==1.2.2" \
        "plotly==4.14.3" \
        "matplotlib==3.3.4" \
        "scikit-learn==0.22.2.post1" \
        "cma==3.0.3" \
        "fakeredis==1.4.5" \
        "setuptools"

# optuna is a flat-layout package imported straight from the working tree: the runner
# invokes pytest with cwd=/optuna, which puts /optuna on sys.path, so there is nothing to
# install.
COPY --from=swesweep-src /src /optuna
WORKDIR /optuna

RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "optuna maxbug source" && git tag baseline

# Prove the suite is green before any patch is applied.
RUN python -m pytest tests/test_distributions.py -q -p no:cacheprovider -o addopts=

CMD ["python", "-c", "import optuna; print('optuna', optuna.__version__)"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
