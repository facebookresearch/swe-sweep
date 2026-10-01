# Maximally-buggy shardingsphere — frozen at anchor 5.2.1.
#
# Built upstream by `pandora construct build-image -t shardingsphere@5.2.1`, which prepares the build
# context under data/tasks/shardingsphere/_local_only/maxbug/5.2.1/context/: it exports the source
# tree at `5.2.1` FROM THE LOCAL CLONE (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md) into ./shardingsphere, and copies this file in as
# ./Dockerfile.
#
# Why JDK 8: shardingsphere 5.x compiles at source level 8 and its CI of the period ran
# JDK 8. The whole reactor is built here rather than a module list — it is modest, and the
# population is spread thinly across features/, infra/, kernel/, proxy/ and jdbc/.

# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/apache/shardingsphere.git /src \
 && git -C /src checkout --quiet 5.2.1 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM docker.io/library/maven:3.9.6-eclipse-temurin-8
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

COPY --from=swesweep-src /src /shardingsphere
WORKDIR /shardingsphere

# Make the exported tree a git repo (the export carries no .git), commit the sources and tag
# them `baseline` — a SOURCE-ONLY tag. The repo's own .gitignore covers `target/`, so the
# runner's `git reset --hard baseline && git clean -fdq` (no -x) resets the sources between
# subtasks while keeping the compiled output below.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "shardingsphere maxbug source" && git tag baseline

# One connection at a time, and retried: these reactors pull thousands of artifacts, and
# maven's default five parallel downloads trip Meta's FwdProxy rate limit within seconds
# (HTTP 429 on CONNECT). Serialized and retried, the same fetch goes through — and because
# maven resumes from what is already in ~/.m2, each attempt starts where the last stopped.
ENV MAVEN_FETCH="-Dmaven.artifact.threads=1 -Dmaven.wagon.http.retryHandler.count=10 \
-Dmaven.wagon.http.retryHandler.requestSentEnabled=true -Dmaven.wagon.rto=120000"
ENV MAVEN_OPTS="-Xmx8g"
ENV SKIPS="-Dcheckstyle.skip=true -Drat.skip=true -Dlicense.skip=true -Dspotbugs.skip=true -Dmaven.javadoc.skip=true -Denforcer.skip=true -Dmaven.source.skip=true"

# Warm ~/.m2 and target/: install the whole reactor. This is what lets a
# reproduction run stay OFFLINE (`mvn -o`) and still recompile the module a patch changed.
RUN for attempt in 1 2 3 4 5 6; do \
        echo "== install attempt $attempt"; \
        mvn -B -DskipTests $SKIPS $MAVEN_FETCH install && exit 0; \
        sleep 60; \
    done; \
    echo "maven could not install the reactor in 6 attempts" >&2; exit 1

# Warm the *test* half too: compiling one suite and running one real test pulls in surefire's
# provider and the test-scope dependencies, which an offline run cannot fetch.
RUN for attempt in 1 2 3; do \
        mvn -B -pl infra/common $SKIPS $MAVEN_FETCH -Dtest=*Test -DfailIfNoTests=false -Dsurefire.failIfNoSpecifiedTests=false test && exit 0; \
        sleep 60; \
    done; \
    echo "maven could not warm the test half" >&2; exit 1

CMD ["mvn", "-v"]
