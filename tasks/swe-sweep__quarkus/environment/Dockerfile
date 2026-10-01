# Maximally-buggy quarkus — frozen at anchor 3.2.0 (tag `3.2.0.Final`).
#
# Built upstream by `pandora construct build-image -t quarkus@3.2.0`, which prepares the build
# context under data/tasks/quarkus/_local_only/maxbug/3.2.0/context/: it exports the source
# tree at `3.2.0.Final` FROM THE LOCAL CLONE (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md) into ./quarkus, and copies this file in as
# ./Dockerfile.
#
# The image's own maven, not `./mvnw`: the wrapper downloads its maven distribution from
# repo.maven.apache.org over a plain URLConnection, which reads neither settings.xml's
# mirror nor its proxy — inside the build container that host does not even resolve.
#
# Why `-Dquickly`: quarkus ships that profile for exactly this — install the whole reactor
# with no tests, no docs, no formatting and no invoker runs. The population is spread over
# dozens of extensions, so there is no useful module subset to pick instead.
#
# Why JDK 17: quarkus 3.x requires it.

# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/quarkusio/quarkus.git /src \
 && git -C /src checkout --quiet 3.2.0.Final \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM docker.io/library/maven:3.9.6-eclipse-temurin-17
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

# Maven's network configuration (see the header for why each half is needed).
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

COPY --from=swesweep-src /src /quarkus
WORKDIR /quarkus

# Make the exported tree a git repo (the export carries no .git), commit the sources and tag
# them `baseline` — a SOURCE-ONLY tag. The repo's own .gitignore covers `target/`, so the
# runner's `git reset --hard baseline && git clean -fdq` (no -x) resets the sources between
# subtasks while keeping the compiled output below.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "quarkus maxbug source" && git tag baseline

# One connection at a time, and retried: these reactors pull thousands of artifacts, and
# maven's default five parallel downloads trip Meta's FwdProxy rate limit within seconds
# (HTTP 429 on CONNECT). Serialized and retried, the same fetch goes through — and because
# maven resumes from what is already in ~/.m2, each attempt starts where the last stopped.
ENV MAVEN_FETCH="-Dmaven.artifact.threads=1 -Dmaven.wagon.http.retryHandler.count=10 \
-Dmaven.wagon.http.retryHandler.requestSentEnabled=true -Dmaven.wagon.rto=120000"
ENV MAVEN_OPTS="-Xmx8g"
ENV SKIPS="-Dformat.skip=true -Dformatter.skip=true -Dimpsort.skip=true -Dinvoker.skip=true -Dcheckstyle.skip=true -Dforbiddenapis.skip=true -Dmaven.javadoc.skip=true -Denforcer.skip=true -Dmaven.source.skip=true"

# `--fail-never` is what lets the reactor install at all — the maven analogue of the
# `--no-bail` aws-cdk's build needs.
#
# Quarkus's **Gradle tooling** modules shell out to Gradle during the build:
# `quarkus-gradle-model` runs `gradle`, and `project-core-extension-codestarts` runs
# `gradlew init` to generate a wrapper into a project template. Gradle's first act is to
# fetch a distribution from services.gradle.org, which the egress filter refuses, so both
# goals exit 1 and take the whole reactor down with them. `-Dexec.skip=true` does not help:
# the executions are configured in the poms and run regardless.
#
# > **Those modules are therefore not installed**, and neither is anything that depends on
# > them — the Gradle plugin and the parts of devtools built on it. A subtask touching one
# > will report a build failure rather than a verdict. devtools is 7 of this anchor's 601
# > touched files and the population lives in `extensions` and `integration-tests`, so the
# > cost is small, but it is not zero.
#
# `--fail-never` exits 0 no matter how much failed, so the guard below is what actually
# decides whether the image is usable.
ENV FAIL_NEVER="--fail-never"

# Warm ~/.m2 and target/: install the whole reactor, via quarkus's own `-Dquickly` fast path. This is what lets a
# reproduction run stay OFFLINE (`mvn -o`) and still recompile the module a patch changed.
# The guard --fail-never needs, and it is written above the RUN rather than inside it: a `#`
# line inside a `\`-continued RUN is joined into a single command line, so it would comment
# out everything after it — including the guard. A handful of Gradle-tooling modules are
# expected to fail; the reactor's own core is not. If quarkus-core is missing from ~/.m2 the
# install did not really happen, and an image built on it would report every subtask as a
# build failure rather than as a bug.
RUN for attempt in 1 2 3 4 5 6; do \
        echo "== install attempt $attempt"; \
        mvn -B -Dquickly $FAIL_NEVER $MAVEN_FETCH; \
        if [ -d /root/.m2/repository/io/quarkus/quarkus-core ]; then exit 0; fi; \
        sleep 60; \
    done; \
    echo "maven could not install the reactor in 6 attempts" >&2; exit 1

# Warm the *test* half too: compiling one suite and running one real test pulls in surefire's
# provider and the test-scope dependencies, which an offline run cannot fetch.
RUN for attempt in 1 2 3; do \
        mvn -B -pl core/runtime $SKIPS $MAVEN_FETCH -Dtest=*Test -DfailIfNoTests=false -Dsurefire.failIfNoSpecifiedTests=false test && exit 0; \
        sleep 60; \
    done; \
    echo "maven could not warm the test half" >&2; exit 1

CMD ["mvn", "-v"]
