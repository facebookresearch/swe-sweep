# Maximally-buggy DolphinScheduler at the 3.2.1 anchor.

# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/apache/dolphinscheduler.git /src \
 && git -C /src checkout --quiet 3.2.1 \
 && if [ -f /src/.gitmodules ]; then git -C /src config -f .gitmodules --get-regexp '^submodule\..*\.path$' | while read -r _key path; do case "$path" in *) echo "skipping submodule $path";; *) git -C /src submodule update --init --recursive --quiet -- "$path" || exit 1;; esac; done; fi \
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
    apt-get install -y --no-install-recommends git ca-certificates python3; \
    ln -s /usr/bin/python3 /usr/local/bin/python; \
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

COPY --from=swesweep-src /src /dolphinscheduler
WORKDIR /dolphinscheduler

RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "dolphinscheduler maxbug source" && git tag baseline

ENV MAVEN_FETCH="-Dmaven.artifact.threads=1 -Dmaven.wagon.http.retryHandler.count=10 \
-Dmaven.wagon.http.retryHandler.requestSentEnabled=true -Dmaven.wagon.rto=120000"
ENV MAVEN_OPTS="-Xmx8g"
ENV SKIPS="-DskipTests -Dspotless.skip=true -Dcheckstyle.skip=true -Drat.skip=true \
-Djacoco.skip=true -Dspotbugs.skip=true -Dmaven.javadoc.skip=true \
-Dmaven.source.skip=true -Dlicense.skip=true -Denforcer.skip=true"

RUN for attempt in 1 2 3 4 5 6; do \
        mvn -B $SKIPS $MAVEN_FETCH install && exit 0; \
        sleep 60; \
    done; \
    echo "maven could not install the reactor in 6 attempts" >&2; exit 1

# Warm surefire and test-scope dependencies on a small, stable module. Reproduction runs
# offline and Maven will not fetch a missing provider there.
RUN for attempt in 1 2 3; do \
        mvn -B -pl dolphinscheduler-common \
          -Dspotless.skip=true -Dcheckstyle.skip=true -Drat.skip=true \
          -Djacoco.skip=true -Dspotbugs.skip=true -Dmaven.javadoc.skip=true \
          -Dmaven.source.skip=true -Dlicense.skip=true -Denforcer.skip=true \
          $MAVEN_FETCH -Dtest=*Test -DfailIfNoTests=false \
          -Dsurefire.failIfNoSpecifiedTests=false test && exit 0; \
        sleep 60; \
    done; \
    echo "maven could not warm the test dependencies" >&2; exit 1

CMD ["mvn", "-v"]
