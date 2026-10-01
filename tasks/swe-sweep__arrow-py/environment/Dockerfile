# Maximally-buggy arrow-py — the 1.0.x anchor candidate (1.0.2).
#
# Same shape as Dockerfile-0.15 (read that header for what the build context is and why
# the tree is installed editable); this one differs only in the era it pins to. 1.0
# dropped Python 2, moved to pytest 6 and dateparser 1.0, so its dependency set is a
# clean generation later and does not resolve on the 0.15 pins.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/arrow-py/arrow.git /src \
 && git -C /src checkout --quiet 1.0.2 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM python:3.9-slim-buster
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# Point apt at the Debian archive (buster is EOL) and install git — needed in-container
# to reset/apply/clean between instances.
RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    printf 'deb http://archive.debian.org/debian buster main\n\
deb http://archive.debian.org/debian-security buster/updates main\n' \
        > /etc/apt/sources.list; \
    apt-get -o Acquire::Check-Valid-Until=false update; \
    apt-get install -y --no-install-recommends git ca-certificates; \
    rm -rf /var/lib/apt/lists/*

# The repo's own requirements.txt at 1.0.2, minus the docs and pre-commit entries.
RUN pip install --no-cache-dir \
        "python-dateutil==2.8.1" \
        "pytz==2019.3" \
        "simplejson==3.17.2" \
        "dateparser==1.0.0" \
        "pytest==6.2.2" \
        "pytest-mock==3.5.1"

COPY --from=swesweep-src /src /arrow
WORKDIR /arrow

RUN pip install --no-cache-dir --no-deps -e /arrow

RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "arrow maxbug source" && git tag baseline

CMD ["python", "-c", "import arrow; print('arrow', arrow.__version__)"]
