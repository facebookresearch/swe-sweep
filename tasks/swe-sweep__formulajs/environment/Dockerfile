# Maximally-buggy formulajs — frozen at anchor version 4.1.0.
#
# The runner-up candidate to 3.1.6 (20 live subtasks against 24), a year newer: 4.x moved the
# assertions from `should` to `chai` and runs mocha with `--recursive`, so `test/utils/` is in
# the default spec set. Kept in the shortlist because a newer tree usually needs less patch
# rebasing; the reproduction census decides.
#
# See docker/Dockerfile-3.1.6 for what the image is and how it is built.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/formulajs/formulajs.git /src \
 && git -C /src checkout --quiet 4.1.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM node:18-bullseye
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    apt-get update; \
    apt-get install -y --no-install-recommends git ca-certificates python3; \
    ln -sf /usr/bin/python3 /usr/local/bin/python; \
    rm -rf /var/lib/apt/lists/*

ENTRYPOINT []

COPY --from=swesweep-src /src /formulajs
WORKDIR /formulajs

RUN npm ci --no-audit --no-fund

# Prove the suite is green before any patch is applied — see Dockerfile-3.1.6.
RUN npx --no-install mocha test/logical.js --exit --timeout 60000

RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "formulajs maxbug source" && git tag baseline

CMD ["node", "-e", "console.log('formulajs', require('/formulajs/package.json').version)"]
