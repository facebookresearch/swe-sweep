# Maximally-buggy gson — the 2.8.0 anchor.
#
# gson is a single-module maven reactor (`<modules><module>gson</module></modules>`), so
# there is nothing to select with `-pl` beyond that one module and the warm build is
# quick. `extras/`, `proto/`, `metrics/` and `codegen/` sit in the tree but are NOT in the
# reactor at any 2.8.x tag; a subtask whose test lives there reports "no targets" rather
# than failing.
#
# JDK 8, not something newer: 2.8.0's pom sets `maven.compiler.source/target` to 1.6, which
# javac refuses from JDK 12 on and warns about from 9. Reflection over the JDK *is* gson's
# bug surface (see `task.yaml`), so the JDK is part of the environment under test and is
# pinned rather than tracked. This is also why the file is named for the 2.8 line but only
# 2.8.0 uses it: from 2.8.1 the pom compiles `module-info.java` through a `jdkToolchain` at
# `--release 9`, which JDK 8 has no flag for.

# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/google/gson.git /src \
 && git -C /src checkout --quiet gson-parent-2.8.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM docker.io/library/maven:3.8.8-eclipse-temurin-8
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    apt-get update; \
    apt-get install -y --no-install-recommends git ca-certificates; \
    rm -rf /var/lib/apt/lists/*

# Mirror central through GCS and teach maven the build-time proxy, if there is one.
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

COPY --from=swesweep-src /src /gson
WORKDIR /gson

# The export carries no `.git`; make one and tag the sources `baseline` so the runner can
# `git reset --hard baseline && git clean -fdq` between subtasks. `.gitignore` covers
# `target/`, so the compiled output below survives that reset.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "gson maxbug source" && git tag baseline

# One connection at a time, and retried: maven's default five parallel downloads trip
# Meta's FwdProxy rate limit within seconds (HTTP 429 on CONNECT).
ENV MAVEN_FETCH="-Dmaven.artifact.threads=1 -Dmaven.wagon.http.retryHandler.count=10 \
-Dmaven.wagon.http.retryHandler.requestSentEnabled=true -Dmaven.wagon.rto=120000"
ENV MAVEN_OPTS="-Xmx2g"
ENV SKIPS="-Dmaven.javadoc.skip=true -Dmaven.source.skip=true -Denforcer.skip=true \
-Dlicense.skip=true -Dgpg.skip=true -Danimal.sniffer.skip=true"

# Warm ~/.m2 and target/ with the product half, so a reproduction run can stay OFFLINE
# (`mvn -o`) and still recompile the module a patch changed.
RUN for attempt in 1 2 3 4 5 6; do \
        echo "== install attempt $attempt"; \
        mvn -B -DskipTests $SKIPS $MAVEN_FETCH install && exit 0; \
        sleep 60; \
    done; \
    echo "maven could not install the reactor in 6 attempts" >&2; exit 1

# Warm the *test* half too. Compiling the suite and running one real test is what pulls in
# surefire's JUnit4 provider and the test-scope dependencies; an offline run cannot fetch
# them, and the provider is not a dependency of the `install` above, so without this step
# every subtask dies with "surefire-junit4 ... has not been downloaded".
RUN for attempt in 1 2 3; do \
        mvn -B $SKIPS $MAVEN_FETCH \
          -Dtest=CommentsTest -DfailIfNoTests=false \
          -Dsurefire.failIfNoSpecifiedTests=false test && exit 0; \
        sleep 60; \
    done; \
    echo "maven could not warm the test dependencies" >&2; exit 1

CMD ["mvn", "-v"]
