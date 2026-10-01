# Maximally-buggy Apache Pulsar, frozen at v2.10.1.
#
# Pulsar 2.10 supports JDK 11 and Maven 3.6+. The core-modules profile covers the Java
# reactor that dominates the candidate population while avoiding release assemblies,
# Docker images, and other distribution-only work.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/apache/pulsar.git /src \
 && git -C /src checkout --quiet v2.10.1 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM docker.io/library/maven:3.8.8-eclipse-temurin-11
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

COPY --from=swesweep-src /src /pulsar
WORKDIR /pulsar

# Keep the compiled reactor and Maven cache across subtask resets. The source-only baseline
# is committed before the build; Pulsar's .gitignore excludes every target/ directory.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "pulsar maxbug source" && git tag baseline

# Maven itself does not honor the standard proxy variables. Use the Google mirror to avoid
# Maven Central's shared-proxy rate limit and serialize artifact downloads so retries make
# forward progress instead of amplifying throttling.
ENV MAVEN_FETCH="-Dmaven.artifact.threads=1 -Dmaven.wagon.http.retryHandler.count=10 \
-Dmaven.wagon.http.retryHandler.requestSentEnabled=true -Dmaven.wagon.rto=120000"
ENV MAVEN_OPTS="-Xmx12g -Dhttp.keepAlive=false -Dmaven.wagon.http.pool=false"
ENV PULSAR_SKIPS="-DskipTests -Dcheckstyle.skip=true -Drat.skip=true \
-Dlicense.skip=true -Dspotbugs.skip=true -Dmaven.javadoc.skip=true \
-Dmaven.source.skip=true -Denforcer.skip=true -DskipDocker=true \
-DskipBuildDistribution=true"

# This is the same reduced reactor used by Pulsar's unit-test CI. Repeated attempts are
# deliberate: the project resolves thousands of artifacts, and Maven resumes from ~/.m2.
RUN for attempt in 1 2 3 4 5 6; do \
        echo "== core reactor install attempt $attempt"; \
        mvn -B -ntp -Pcore-modules,-main $PULSAR_SKIPS $MAVEN_FETCH install && exit 0; \
        sleep 60; \
    done; \
    echo "maven could not install the core reactor in 6 attempts" >&2; exit 1

# Warm surefire/TestNG and test-scope dependencies for a small core module. Census runs are
# offline, so the provider must already be present in the image.
RUN for attempt in 1 2 3; do \
        mvn -B -ntp -Pcore-modules,-main -pl pulsar-common $PULSAR_SKIPS \
          $MAVEN_FETCH -DskipTests=false -Dtest=*Test -DfailIfNoTests=false \
          -Dsurefire.failIfNoSpecifiedTests=false test && exit 0; \
        sleep 60; \
    done; \
    echo "maven could not warm the test dependencies" >&2; exit 1

CMD ["mvn", "-v"]
