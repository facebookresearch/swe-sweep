# Maximally-buggy netty — frozen at candidate anchor version netty-4.1.18.Final.
#
# Built upstream by `pandora construct build-image -t netty@4.1.18`, which prepares the build
# context under data/netty/maxbug/4.1.18/context/: it exports the netty source tree at
# netty-4.1.18.Final FROM THE LOCAL CLONE (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md) into ./netty, and copies this file in as
# ./Dockerfile.
#
# Why 4.1.18.Final: netty's bug-coverage curve peaks in December 2017 at 180 live
# subtasks, and netty-4.1.18.Final (2017-12-08) is the release tag on that peak, with 178
# — more than any other tag. Unlike the Rust cohort there is no reason to trade coverage
# for modernity here: maven resolves against the versions the poms pin, so a 2017 tree
# still builds the 2017 dependency set.
#
# Why JDK 8: netty 4.1.18 predates the module system and compiles with `source/target
# 1.6`, which javac rejects from JDK 12 on. maven:3.8.6-openjdk-8 is the period-correct
# pairing and the one this recipe was validated against.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/netty/netty.git /src \
 && git -C /src checkout --quiet netty-4.1.18.Final \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM docker.io/library/maven:3.8.6-openjdk-8-slim
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        git ca-certificates python3 python-is-python3; \
    rm -rf /var/lib/apt/lists/*
# The Python alias is retained only for repository-owned tooling; benchmark control runs on the host.

# Maven's network configuration, written at build time into a settings.xml:
#
# - **A mirror of Maven Central.** `repo.maven.apache.org` is rate-limited fleet-wide at
#   Meta's FwdProxy ("global_hostname_rps_override"), and netty 4.1 needs several hundred
#   artifacts, so a build against it never finishes — worse, a throttled response arrives
#   as an empty HTTP 200 that maven caches as a corrupt artifact. Google's mirror of
#   Central serves the identical bytes and is not throttled.
# - **The proxy.** Maven reads no `*_proxy` env var; it wants the JVM's proxy properties.
#   Derived from whatever the build environment forwarded in, so the same Dockerfile
#   builds unchanged on a host with direct egress.
RUN set -eux; \
    mkdir -p /root/.m2; \
    { \
      echo '<settings><mirrors>'; \
      echo '  <mirror><id>central-gcs</id><mirrorOf>central</mirrorOf>'; \
      echo '    <url>https://maven-central.storage-download.googleapis.com/maven2</url></mirror>'; \
      echo '</mirrors>'; \
      if [ -n "${http_proxy:-${HTTP_PROXY:-}}" ]; then \
        url="${http_proxy:-$HTTP_PROXY}"; \
        host=$(echo "$url" | sed -E 's#^[a-z]+://##; s#:.*##'); \
        port=$(echo "$url" | sed -E 's#.*:##; s#/.*##'); \
        echo '<proxies>'; \
        echo "  <proxy><id>p-http</id><active>true</active><protocol>http</protocol><host>$host</host><port>$port</port><nonProxyHosts>localhost|127.0.0.1</nonProxyHosts></proxy>"; \
        echo "  <proxy><id>p-https</id><active>true</active><protocol>https</protocol><host>$host</host><port>$port</port><nonProxyHosts>localhost|127.0.0.1</nonProxyHosts></proxy>"; \
        echo '</proxies>'; \
      fi; \
      echo '</settings>'; \
    } > /root/.m2/settings.xml

# netty source tree at the candidate ref, exported from the local clone into the build
# context (see the header).
COPY --from=swesweep-src /src /netty
WORKDIR /netty

# Make the exported tree a git repo (the export carries no .git), commit the source and
# tag it `baseline` — a SOURCE-ONLY tree. netty's own .gitignore covers `target/`, so the
# consumers' `git reset --hard baseline && git clean -fdq` (no -x) resets the sources
# between subtasks while keeping the compiled output below.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "netty maxbug source" && git tag baseline

# Warm ~/.m2 and target/: install every module the subtask population actually touches,
# plus everything they build on (-am). This is what lets a reproduction run stay OFFLINE
# and still recompile the module a patch changed.
#
# The list is the pure-Java reactor. The JNI transports (transport-native-epoll and
# friends) are left out on purpose: they need an autotools toolchain to build their C, and
# a subtask that touches one is reported as a build failure rather than being allowed to
# fail the whole image.
#
# The quality plugins are skipped throughout — checkstyle, forbidden-apis, animal-sniffer
# and japicmp police contribution style and API compatibility, which is not what the
# benchmark measures, and they are a large share of the build's wall clock.
ENV NETTY_SKIPS="-Dcheckstyle.skip -Dxml.skip -Danimal.sniffer.skip -Dmaven.javadoc.skip \
-Denforcer.skip -Dforbiddenapis.skip -Dlicense.skip -Dspotbugs.skip -Dfindbugs.skip \
-Djapicmp.skip -Dmaven.source.skip"
ENV NETTY_MODULES="common,buffer,transport,transport-sctp,transport-udt,codec,codec-dns,\
codec-haproxy,codec-http,codec-http2,codec-memcache,codec-mqtt,codec-redis,codec-smtp,\
codec-socks,codec-stomp,codec-xml,handler,handler-proxy,resolver,resolver-dns,testsuite"

# One connection at a time, and retried: netty 4.1.18 pulls several hundred artifacts,
# and maven's default five parallel downloads trip Meta's FwdProxy rate limit for
# repo.maven.apache.org within seconds (HTTP 429 on CONNECT). Serialized and retried, the
# same fetch goes through — and because maven resumes from what is already in ~/.m2, each
# attempt starts where the last one stopped.
ENV MAVEN_FETCH="-Dmaven.artifact.threads=1 -Dmaven.wagon.http.retryHandler.count=10 \
-Dmaven.wagon.http.retryHandler.requestSentEnabled=true -Dmaven.wagon.rto=120000"
RUN for attempt in 1 2 3 4 5 6; do \
        echo "== dependency fetch attempt $attempt"; \
        mvn -B -pl "$NETTY_MODULES" -am -DskipTests $NETTY_SKIPS $MAVEN_FETCH install && exit 0; \
        sleep 60; \
    done; \
    echo "maven could not fetch its dependencies in 6 attempts" >&2; exit 1

# Warm the *test* half too: compiling the suites and running one real test pulls in
# surefire's provider and the test-scope dependencies, which an offline run cannot fetch.
RUN for attempt in 1 2 3; do \
        mvn -B -pl common $NETTY_SKIPS $MAVEN_FETCH -Dtest=AsciiStringCharacterTest \
            -DfailIfNoTests=false test && exit 0; \
        sleep 60; \
    done; \
    echo "maven could not warm the test half" >&2; exit 1

CMD ["mvn", "-v"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
