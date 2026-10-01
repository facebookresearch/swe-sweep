# Maximally-buggy PhpSpreadsheet — frozen at anchor version 1.13.0.
#
# Built upstream by `pandora construct build-image -t phpspreadsheet@1.13.0`, which prepares the build
# context from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the source tree at 1.13.0 into
# ./phpspreadsheet and copies this file in as ./Dockerfile. The image holds the tree with a
# `baseline` commit+tag; the host-controlled evaluator
# (tasks/phpspreadsheet/task.yaml) does `git reset --hard baseline`, then applies
# the per-bug test/gold patches.
#
# Why 1.13.0: both patches apply for 16 subtasks here, against 12 at 1.26.0, 11 at the curve
# peak 1.9.0, 8 at 1.29.0 and at 2.1.0, 7 at 1.17.1 and 6 at 3.5.0. It also sits on the flat
# top of the curve (40 live), so it is the best of both.
#
# Why PHP 7.4: composer.json requires ^7.2 and 1.13.0 is May 2020, so 7.4 is the newest
# period-correct interpreter — and the one PHPUnit 8.5 and the committed lock were built for.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/PHPOffice/PhpSpreadsheet.git /src \
 && git -C /src checkout --quiet 1.13.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM php:7.4-cli-bullseye
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# Built at Meta through FwdProxy: `pandora construct build-image` wraps the build in
# `sudo with-proxy` with `--network=host`, and apt's unprivileged `_apt` sandbox user cannot
# read a proxied download — so apt is told to run as root before it touches the network (see
# docs/ai/030-debug/260626-maxbug-image-registry-blocked.md).
#
# The PHP image already has ctype/dom/iconv/fileinfo/libxml/mbstring/simplexml/xml/xmlreader/
# xmlwriter/zlib. `gd` and `zip` are the two composer.json asks for that it does not, and the
# suite genuinely needs both: gd for the chart/drawing tests, zip for every xlsx round-trip.
RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        git ca-certificates curl unzip python3 \
        libzip-dev libpng-dev libjpeg-dev libfreetype6-dev; \
    docker-php-ext-configure gd --with-jpeg --with-freetype; \
    docker-php-ext-install -j"$(nproc)" gd zip; \
    ln -sf /usr/bin/python3 /usr/local/bin/python; \
    rm -rf /var/lib/apt/lists/*

# composer is installed with its own installer, run by *this image's* PHP — see
# tasks/dbal/docker/Dockerfile-3.0.0 for why neither `COPY --from=composer:2` nor Debian's
# package works here. curl rather than PHP's `copy()` because the build runs behind FwdProxy
# and PHP's stream wrappers do not honour http_proxy.
RUN set -eux; \
    curl -fsSL -o /tmp/composer-setup.php https://getcomposer.org/installer; \
    php /tmp/composer-setup.php --install-dir=/usr/local/bin --filename=composer --2; \
    rm /tmp/composer-setup.php; \
    composer --version

COPY --from=swesweep-src /src /phpspreadsheet
WORKDIR /phpspreadsheet

# `composer install` honours the committed composer.lock, which is what makes this
# period-correct: the lock decides every version, not today's packagist. The census container
# has no network, so everything the suite needs has to be in vendor/ already. `--no-plugins`
# because composer 2.2 refuses any plugin not listed under `allow-plugins`, and a May 2020
# tree predates that key — the blocked plugin only wires up the linter, which is not graded.
RUN composer install --no-interaction --no-progress --prefer-dist --no-plugins

# Prove the suite is green *before* any patch is applied. A pristine failure reads as
# `fails_pre_gold` for every subtask and would quietly inflate the whole census; catching it
# at image-build time is the cheapest place. One calculation-engine class — the family most
# of this task's bugs are in, and the one that exercises the data-provider fixtures under
# tests/data/.
RUN vendor/bin/phpunit --configuration phpunit.xml.dist \
        tests/PhpSpreadsheetTests/Calculation/Functions/MathTrig/SumIfTest.php

RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "phpspreadsheet maxbug source" && git tag baseline

CMD ["php", "-r", "echo \\PhpOffice\\PhpSpreadsheet\\Document\\Properties::class, PHP_EOL;"]
