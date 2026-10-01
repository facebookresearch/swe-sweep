# Maximally-buggy rails/rails — frozen at a 7.0.x candidate anchor.
#
# Built upstream by `pandora construct build-image -t rails@<v>`, which prepares the build context
# from the local clone (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md): it exports the source tree at the candidate
# tag into ./rails and copies this file in as ./Dockerfile. The image holds the tree with a
# `baseline` commit+tag; the host-controlled runner (tasks/rails/task.yaml) does
# `git reset --hard baseline`, then applies the per-bug test/gold patches.
#
# Why 7.0.x: the coverage curve peaks on 2021-11-02 at 322 live subtasks — the largest of
# any task in this batch by a factor of three — and v7.0.0 (2021-12-15) is the release tag
# on that shoulder with 320.
#
# Why ruby:3.0-bullseye: Rails 7.0 supports 2.7 through 3.1, and its CI of the period ran
# 3.0. 3.1 was released the same month as 7.0.0 and is not what the lockfile was resolved
# against.
#
# Built at Meta through FwdProxy: `pandora construct build-image` wraps the build in
# `sudo with-proxy` with `--network=host`, and apt's unprivileged `_apt` sandbox user
# cannot read a proxied download — so apt is told to run as root before it touches the
# network (see docs/ai/030-debug/260626-maxbug-image-registry-blocked.md).
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/rails/rails.git /src \
 && git -C /src checkout --quiet v7.0.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM ruby:3.0-bullseye
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# sqlite3 is the adapter Active Record's suite defaults to (`ARCONN`); the rest are what
# the native gems in the lockfile link against. git supports the host-directed reset/apply.
RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        git ca-certificates curl python3 \
        libsqlite3-dev sqlite3 libyaml-dev libffi-dev libxml2-dev libxslt1-dev; \
    rm -rf /var/lib/apt/lists/*

COPY --from=swesweep-src /src /rails
WORKDIR /rails

# Every gem's `bin/test` is the entry point the runner invokes, and the exec bit does not
# survive the way the AWS builder stages the context through S3 — so the build succeeds
# locally and fails on Batch with "bundler: not executable: bin/test". Restoring it here,
# *before* the baseline commit, also means git records the mode, so the runner's
# `git reset --hard baseline` cannot lose it again.
RUN chmod +x */bin/test

# `db`, `rubocop` and `doc` are dropped. `db` is the reason: it pulls `mysql2` straight
# from a GitHub ref, which this build cannot fetch, and it only adds the MySQL and
# PostgreSQL adapters — Active Record's suite runs on sqlite3 unless `ARCONN` says
# otherwise, so dropping them costs the non-default adapter tests and nothing else.
#
# The committed Gemfile.lock decides every other version, which is what makes the image
# period-correct rather than "whatever rubygems serves today".
RUN set -eux; \
    bundle config set --local without 'db rubocop doc'; \
    bundle config set silence_root_warning true; \
    bundle install -j"$(nproc)"

# Prove the suite is green *before* any patch is applied. A pristine failure reads as
# `fails_pre_gold` for every subtask and would quietly inflate the whole census; catching
# it at image-build time is the cheapest place to do it. One file from each of the three
# gems that carry most of the bugs, because each gem has its own test helper and load path
# and can break independently of the others.
RUN set -eux; \
    (cd activesupport && bundle exec bin/test test/core_ext/string_ext_test.rb); \
    (cd activerecord && bundle exec bin/test test/cases/base_test.rb); \
    (cd actionpack && bundle exec bin/test test/dispatch/mime_type_test.rb)

RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "rails maxbug source" && git tag baseline

CMD ["ruby", "--version"]
