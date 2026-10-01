# Maximally-buggy tinygrad — frozen at anchor version v0.12.0 (2026-01-12).
#
# Built upstream by `pandora construct build-image -t tinygrad@v0.12.0`, which prepares the build
# context from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the source tree at v0.12.0
# into ./tinygrad and copies this file in as ./Dockerfile. The image holds the tree with
# a `baseline` commit+tag; the host-controlled evaluator
# (tasks/tinygrad/task.yaml) does `git reset --hard baseline`, then applies the
# per-bug test/gold patches.
#
# tinygrad is PURE PYTHON: no build step, `baseline` is the whole truth, and the runner
# passes needs_build=False.
#
# **torch is the oracle, so it is not an optional dependency here.** `test/test_ops.py`
# runs every operation against `torch` and asserts the two agree to a tolerance, which is
# what makes a scheduling or shape-tracker defect an automatically detectable numerical
# divergence rather than a judgement call. The CPU wheel is what the image installs; the
# pin is the one this tag's `testing_minimal` extra names, so the reference is
# period-correct too.
#
# clang is the CPU backend's code generator: tinygrad compiles each kernel to C and shells
# out to a compiler, so without it every device test errors instead of running.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/tinygrad/tinygrad.git /src \
 && git -C /src checkout --quiet v0.12.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM python:3.12-slim-bookworm
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends git ca-certificates clang; \
    rm -rf /var/lib/apt/lists/*

# The CPU torch wheel, from PyTorch's own index — the default PyPI wheel drags in the
# whole CUDA stack for hardware the container does not have.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu "torch==2.9.1"
RUN pip install --no-cache-dir \
        "numpy" \
        "pytest" \
        "pytest-xdist" \
        "pytest-timeout" \
        "hypothesis>=6.148.9" \
        "z3-solver" \
        "tqdm" \
        "pillow" \
        "setuptools"

# tinygrad is imported straight from the working tree: the runner invokes pytest with
# cwd=/tinygrad, which puts /tinygrad on sys.path, so there is nothing to install.
COPY --from=swesweep-src /src /tinygrad
WORKDIR /tinygrad

RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "tinygrad maxbug source" && git tag baseline

# CPU is the only backend in the container. tinygrad picks its device from the
# environment, and left unset it probes for GPUs, fails, and reports a device error in
# place of every test result.
ENV CPU=1
ENV PYTHONDONTWRITEBYTECODE=1

CMD ["python", "-c", "from tinygrad import Tensor; print(Tensor([1,2,3]).sum().item())"]
