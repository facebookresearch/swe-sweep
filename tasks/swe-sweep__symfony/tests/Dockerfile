# Maximally-buggy symfony/symfony — frozen at anchor version v6.4.0.
#
# Built upstream by `pandora construct build-image -t symfony@v6.4.0`, which prepares the build
# context from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the source tree at v6.4.0 into
# ./symfony and copies this file in as ./Dockerfile. The image holds the tree with a
# `baseline` commit+tag; the host-controlled evaluator (tasks/symfony/task.yaml) does
# `git reset --hard baseline`, then applies the per-bug test/gold patches.
#
# Why PHP 8.2: v6.4.0's composer.json requires >=8.1 and the tag is November 2023, so 8.2 is
# the release Symfony's own CI ran that branch on.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/symfony/symfony.git /src \
 && git -C /src checkout --quiet v6.4.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM php:8.2-cli-bookworm
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# Built at Meta through FwdProxy: `pandora construct build-image` wraps the build in
# `sudo with-proxy podman build` with `--network=host`, and apt's unprivileged `_apt`
# sandbox user cannot read a proxied download — so apt is told to run as root before it
# touches the network (see docs/ai/030-debug/260626-maxbug-image-registry-blocked.md).
#
# The extensions are what the *suite* reaches for beyond composer.json's own floor:
# `intl` for Intl/Translation/Validator, `xsl` for the XML config loaders, `sodium` and
# `gmp` for Security, `zip`/`gd` for HttpFoundation's file handling, `sockets` and `pcntl`
# for Process and Messenger, `bcmath` for the numeric validators.
#
# No Redis, memcached, LDAP, MongoDB or a real database. phpunit.xml.dist points those at
# localhost and the families skip when nothing answers.
RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        git ca-certificates curl unzip python3 \
        libicu-dev libzip-dev libxml2-dev libxslt1-dev libcurl4-openssl-dev \
        libpng-dev libjpeg-dev libfreetype6-dev libgmp-dev libsodium-dev; \
    docker-php-ext-configure gd --with-jpeg --with-freetype; \
    docker-php-ext-install -j"$(nproc)" intl zip gd gmp xsl sodium sockets pcntl bcmath; \
    ln -sf /usr/bin/python3 /usr/local/bin/python; \
    rm -rf /var/lib/apt/lists/*

# composer is installed with its own installer, run by *this image's* PHP — see
# tasks/dbal/docker/Dockerfile-3.0.0 for why neither `COPY --from=composer:2` nor Debian's
# package works here. curl rather than PHP's `copy()` because the build runs behind FwdProxy
# and PHP's stream wrappers do not honour http_proxy.
#
# `policy.advisories.block` is turned off: it refuses any release with a security advisory
# against it, and a period-correct dependency set from 2023 is made almost entirely of
# superseded releases, so the gate can never be satisfied here.
RUN set -eux; \
    curl -fsSL -o /tmp/composer-setup.php https://getcomposer.org/installer; \
    php /tmp/composer-setup.php --install-dir=/usr/local/bin --filename=composer --2; \
    rm /tmp/composer-setup.php; \
    composer config --global policy.advisories.block false; \
    composer --version

COPY --from=swesweep-src /src /symfony
WORKDIR /symfony

# The deprecation helper turns every triggered deprecation into a test failure, and a tree
# frozen three years before its dependency set is resolved will trigger some. Symfony's own
# `./phpunit` wrapper does the same thing when it runs inside the PhpUnit bridge's directory.
ENV SYMFONY_DEPRECATIONS_HELPER=disabled

# Two things composer cannot work out for itself in a monorepo exported from git archive:
#
# - `COMPOSER_ROOT_VERSION` — composer.json `replace`s every component at `self.version`, so
#   without a root version it guesses 1.0.0 and no requirement can be satisfied.
# - the `git init` below, and its **branch name**. composer.json declares two `path`
#   repositories (`src/Symfony/Contracts`, `src/Symfony/Component/Runtime`) and asks the VCS
#   for their version. `Contracts` is pinned inline in composer.json; `Runtime` is not, so on
#   a tree with no git metadata it resolves to `dev-main` and the root's `6.4.x-dev`
#   requirement is unsatisfiable. Initialising the repo on a branch named `6.4` *before*
#   composer runs is what makes it read `6.4.x-dev`.
ENV COMPOSER_ROOT_VERSION=6.4.x-dev
RUN git init -q -b 6.4 \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "symfony maxbug source (pre-vendor)"

# symfony/symfony ships no composer.lock — it is a library, and `minimum-stability: dev`, so
# the resolver decides the dependency set and picks development branches for some of it.
# That set is frozen the moment this image is built and pushed, which is what makes the
# census repeatable; the pristine check below is what says the set is usable.
# `--no-plugins` for the same reason as the other PHP tasks: the tree does not list every
# plugin under `allow-plugins`, and the ones involved only wire up linters.
RUN composer install --no-interaction --no-progress --prefer-dist --no-plugins

# Symfony does not depend on phpunit directly. `./phpunit` is a wrapper around
# `simple-phpunit` from the in-tree PhpUnit bridge, which *downloads and installs* the
# requested PHPUnit into `SYMFONY_PHPUNIT_DIR` on first use. The grading container has no
# network, so that install has to happen here, at build time. 9.6 is the version the wrapper
# itself defaults to on this branch.
ENV SYMFONY_PHPUNIT_VERSION=9.6
ENV SYMFONY_PHPUNIT_DIR=/symfony/.phpunit
RUN php ./phpunit install

# Prove the suite is green *before* any patch is applied. A pristine failure reads as
# `fails_pre_gold` for every subtask and would quietly inflate the whole census. Four files,
# chosen to cover the parts of the image most likely to be wrong: HttpFoundation (the plain
# unit half), Intl and String (the `intl` extension and its ICU data), and Process (`pcntl`
# and real subprocesses). One file per invocation — PHPUnit 9 takes a single positional
# path, and a second one silently yields "No tests executed".
#
# Not `Intl/Tests/LocalesTest.php`, which looks like the obvious ICU check: phpunit.xml.dist
# excludes the `intl-data` group, so it selects nothing at all.
RUN php ./phpunit src/Symfony/Component/HttpFoundation/Tests/RequestTest.php \
    && php ./phpunit src/Symfony/Component/Intl/Tests/LocaleTest.php \
    && php ./phpunit src/Symfony/Component/String/Tests/UnicodeStringTest.php \
    && php ./phpunit src/Symfony/Component/Process/Tests/ProcessTest.php

# `baseline` is the pre-vendor commit made above, not a second one. Everything composer and
# simple-phpunit produced — `vendor/`, `.phpunit/`, `composer.lock` — is in symfony's own
# `.gitignore`, so there is nothing left to commit here and a plain `git commit` exits 1 with
# "nothing to commit". Nothing is lost: the evaluator's `git reset --hard baseline` only has
# to restore the *source* tree, and untracked vendor files are not touched by it.
RUN git tag baseline && git status --porcelain | head

CMD ["php", "-r", "require '/symfony/vendor/autoload.php'; echo \\Symfony\\Component\\HttpKernel\\Kernel::VERSION, PHP_EOL;"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
