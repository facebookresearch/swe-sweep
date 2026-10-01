# Maximally-buggy micropython — the v1.19.1 anchor (unix port).
#
# **The CPython in this image is part of the environment under test.** `tests/run-tests.py`
# compares the MicroPython output of a test script against a checked-in `<case>.py.exp`
# or, when there is none, against *CPython's own output for the same script*. So the
# interpreter that plays oracle has to be period-correct: a newer CPython changes reprs
# and error text and turns dozens of untouched tests into pristine failures, which the
# census would read as bugs that reproduce. v1.19.1 is June 2022 — 3.10 is its contemporary.
#
# Only the **unix port** is built. micropython's merged PRs are mostly hardware ports
# (stm32, esp32, rp2, nrf) that need the physical board; those subtasks reach the census
# and report "no targets" there rather than being filtered out earlier, which is what
# keeps the funnel honest (see `task.yaml`).

# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/micropython/micropython.git /src \
 && git -C /src checkout --quiet v1.19.1 \
 && if [ -f /src/.gitmodules ]; then git -C /src config -f .gitmodules --get-regexp '^submodule\..*\.path$' | while read -r _key path; do case "$path" in lib/arduino-lib|lib/asf4|lib/btstack|lib/cyw43-driver|lib/fsp|lib/libhydrogen|lib/libmetal|lib/lwip|lib/mynewt-nimble|lib/nrfx|lib/nxp_driver|lib/open-amp|lib/pico-sdk|lib/protobuf-c|lib/stm32lib|lib/tinyusb|lib/wiznet5k) echo "skipping submodule $path";; *) git -C /src submodule update --init --recursive --quiet -- "$path" || exit 1;; esac; done; fi \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM docker.io/library/python:3.10-bullseye
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        build-essential git pkg-config libffi-dev libreadline-dev; \
    rm -rf /var/lib/apt/lists/*

COPY --from=swesweep-src /src /micropython
WORKDIR /micropython

# The export carries no `.git`; make one and tag the sources `baseline` so the runner can
# `git reset --hard baseline && git clean -fdq` between subtasks. The repo's `.gitignore`
# covers `build*/`, so the compiled port below survives that reset and a subtask's rebuild
# is incremental.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "micropython maxbug source" && git tag baseline

# mpy-cross first: the unix port's `tests/` uses it for the .mpy tests, and the port build
# does not make it.
RUN make -C mpy-cross -j "$(nproc)"

# The **coverage** variant, not the standard one — the same build micropython's own CI
# runs the suite against. It is the standard port plus the features the suite needs to
# observe: framebuf, the FAT and littlefs VFS backends, `ure`'s debug hooks and
# `sys.settrace`. Measured on the untouched tree at this anchor:
#
#     standard   827 performed, 827 passed, 56 skipped
#     coverage   875 performed, 875 passed,  8 skipped
#
# Both gates are clean, so the choice is purely how much of the suite is observable — and
# 15 of the 109 skim-accepted subtasks touch a test the standard build skips.
RUN make -C ports/unix VARIANT=coverage -j "$(nproc)"

# `run-tests.py` defaults to ../ports/unix/micropython and shells out to `python3` as the
# oracle. Pin both: the default is the *standard* binary, and leaving it would quietly
# run the census against the smaller feature set.
ENV MICROPY_MICROPYTHON=/micropython/ports/unix/micropython-coverage
ENV MICROPY_CPYTHON3=python3

CMD ["/micropython/ports/unix/micropython-coverage", "-c", "print('ok')"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
