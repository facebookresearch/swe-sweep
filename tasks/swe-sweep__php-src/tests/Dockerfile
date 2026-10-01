# Maximally-buggy php-src — the Debian bookworm recipe.
#
# Built upstream by `pandora construct build-image -t php-src@<v>`, which prepares the build
# context under data/tasks/php-src/maxbug/<v>/context/: it exports the php-src source tree
# at that candidate's tag FROM THE LOCAL CLONE (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md) into ./php-src, and copies this file in as
# ./Dockerfile.
#
# **The Debian release is part of the anchor.** bookworm carries OpenSSL 3.0, which PHP
# only properly supports from 8.1 — on an 8.0 anchor a good part of ext/openssl's suite
# fails on a pristine tree, which would read as `fails_pre_gold` and quietly inflate the
# census. An anchor older than 8.1 needs a bullseye sibling of this file.
#
# Why `apt-get build-dep php8.2` instead of a hand-written list: php-src bundles eighty
# extensions and *silently configures one out* when its dependency is missing — the tests
# for that extension then SKIP rather than fail, which shrinks the census without saying
# so. The distribution's own build dependencies are the maintained version of that list.
#
# The short explicit list after it is what Debian's own PHP package does *not* need but
# this configure line does: Debian links readline against libedit and builds gd against
# the system libgd, so `--with-readline` and the bundled gd both fail to configure on
# build-dep alone. `--enable-dba` likewise wants the Berkeley/GDBM headers.
#
# Built at Meta through FwdProxy like every other maxbug image: `pandora construct
# build-image` wraps the build in `sudo with-proxy` and passes `--network=host` (rootless
# podman can't route to FwdProxy's IPv6 — see
# docs/ai/030-debug/260626-maxbug-image-registry-blocked.md). With FwdProxy in front of
# apt, apt's unprivileged `_apt` sandbox user cannot read the proxied download, so apt is
# told to run as root before it touches the network.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/php/php-src.git /src \
 && git -C /src checkout --quiet php-8.2.12 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM debian:bookworm-slim
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    printf 'Types: deb deb-src\nURIs: http://deb.debian.org/debian\nSuites: bookworm bookworm-updates\nComponents: main\nSigned-By: /usr/share/keyrings/debian-archive-keyring.gpg\n\nTypes: deb deb-src\nURIs: http://deb.debian.org/debian-security\nSuites: bookworm-security\nComponents: main\nSigned-By: /usr/share/keyrings/debian-archive-keyring.gpg\n' \
        > /etc/apt/sources.list.d/debian.sources; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        build-essential git ca-certificates pkg-config \
        autoconf automake libtool bison re2c \
        python3 procps file; \
    apt-get build-dep -y php8.2; \
    apt-get install -y --no-install-recommends \
        libreadline-dev \
        libpng-dev libjpeg-dev libwebp-dev libfreetype-dev libxpm-dev \
        libdb-dev libgdbm-dev; \
    rm -rf /var/lib/apt/lists/*

# php-src source tree at the candidate ref, exported from the local clone into the build
# context (see the header).
COPY --from=swesweep-src /src /php-src
WORKDIR /php-src

# Make the exported tree a git repo (the export carries no .git), commit the source and
# tag it `baseline` — a SOURCE-ONLY tree, so an agent's extracted patch can never carry a
# build artifact.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "php-src maxbug source" && git tag baseline

# php-src builds *inside* its own tree, and a consumer resets a subtask with `git reset
# --hard baseline && git clean -fdq`. That is safe here without any extra exclude file:
# php-src' own .gitignore is exhaustive about the autotools build — the objects, the
# libtool directories, `configure` itself, the generated config headers, the re2c lexers,
# the bison parsers and every SAPI binary — so `git clean` (which does not touch ignored
# files) leaves the build in place and a subtask's rebuild really is incremental.
#
# The extension list is deliberately wide: an extension that is not configured in makes
# its whole test directory SKIP, so every one left out is a slice of the census thrown
# away. The database extensions are built even though no server runs here — their tests
# skip on connect, which is the honest outcome, and the ones that need no server still
# run.
RUN ./buildconf --force \
    && ./configure \
        --disable-cgi \
        --enable-bcmath \
        --enable-calendar \
        --enable-dba \
        --enable-exif \
        --enable-ftp \
        --enable-gd \
        --enable-intl \
        --enable-mbstring \
        --enable-opcache \
        --enable-pcntl \
        --enable-shmop \
        --enable-soap \
        --enable-sockets \
        --enable-sysvmsg \
        --enable-sysvsem \
        --enable-sysvshm \
        --with-bz2 \
        --with-curl \
        --with-ffi \
        --with-gettext \
        --with-iconv \
        --with-libxml \
        --with-mysqli \
        --with-openssl \
        --with-pdo-mysql \
        --with-pdo-sqlite \
        --with-readline \
        --with-sodium \
        --with-sqlite3 \
        --with-xsl \
        --with-zip \
        --with-zlib \
    && make -j "$(nproc)"

# run-tests.php tests whatever interpreter runs it, so the suite is always the build in
# this tree — see the `phpt` suite adapter.
CMD ["sapi/cli/php", "run-tests.php", "--help"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
