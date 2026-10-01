# Maximally-buggy nacos — frozen at anchor 3.0.2.
#
# Built upstream by `pandora construct build-image -t nacos@3.0.2`, which prepares the build context
# under data/tasks/nacos/_local_only/maxbug/3.0.2/context/: it exports the source tree at the
# `3.0.2` tag FROM THE LOCAL CLONE (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md) into ./nacos, and copies this file in as
# ./Dockerfile.
#
# Why 3.0.2: it is the interior maximum of the `patch-applies` probe (44 subtasks with both
# patches applying, against 42 at 3.0.0 and 37 at 3.0.3). nacos restructured its modules for
# 3.0, so the 2.x candidates are far behind. See
# docs/ai/040-experiments/nacos/260819-anchor-choice.md.
#
# Why JDK 17: the reactor's own `<java.version>` is 17 at this tag.
#
# The image's own maven, not `./mvnw`: the wrapper downloads its distribution from
# repo.maven.apache.org over a plain URLConnection, which reads neither settings.xml's mirror
# nor its proxy — inside the build container that host does not even resolve. Same reason as
# quarkus and keycloak.

# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/alibaba/nacos.git /src \
 && git -C /src checkout --quiet 3.0.2 \
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

# Maven's network configuration: a mirror that the egress filter allows, plus the host's
# proxy if there is one.
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

COPY --from=swesweep-src /src /nacos
WORKDIR /nacos

# Make the exported tree a git repo (the export carries no .git), commit the sources and tag
# them `baseline` — a SOURCE-ONLY tag. The repo's own .gitignore covers `target/`, so the
# runner's `git reset --hard baseline && git clean -fdq` (no -x) resets the sources between
# subtasks while keeping the compiled output below.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "nacos maxbug source" && git tag baseline

# One connection at a time, and retried: this reactor pulls thousands of artifacts, and
# maven's default five parallel downloads trip Meta's FwdProxy rate limit within seconds
# (HTTP 429 on CONNECT). Serialized and retried, the same fetch goes through — and because
# maven resumes from what is already in ~/.m2, each attempt starts where the last stopped.
ENV MAVEN_FETCH="-Dmaven.artifact.threads=1 -Dmaven.wagon.http.retryHandler.count=10 \
-Dmaven.wagon.http.retryHandler.requestSentEnabled=true -Dmaven.wagon.rto=120000"
ENV MAVEN_OPTS="-Xmx8g"
ENV SKIPS="-Dcheckstyle.skip=true -Dpmd.skip=true -Dmaven.javadoc.skip=true -Denforcer.skip=true -Dmaven.source.skip=true -Dlicense.skip=true -Drat.skip=true -Dgpg.skip=true"

# Warm ~/.m2 and every module's target/: install the whole reactor with tests skipped. This
# is what lets a reproduction run stay OFFLINE (`mvn -o`) and still recompile the module a
# patch changed. `install`, not `package`: nacos modules depend on their siblings' installed
# artifacts, and the runner resolves them from the reactor.
RUN for attempt in 1 2 3 4 5 6; do \
        echo "== install attempt $attempt"; \
        mvn -B -DskipTests $SKIPS $MAVEN_FETCH install && exit 0; \
        sleep 60; \
    done; \
    echo "maven could not install the reactor in 6 attempts" >&2; exit 1

# Warm the *test* half too: compiling one suite and running one real test pulls in surefire's
# provider and the test-scope dependencies, which an offline run cannot fetch.
RUN for attempt in 1 2 3; do \
        mvn -B -pl common $SKIPS $MAVEN_FETCH -Dtest=*Test -DfailIfNoTests=false -Dsurefire.failIfNoSpecifiedTests=false test && exit 0; \
        sleep 60; \
    done; \
    echo "maven could not warm the test half" >&2; exit 1

CMD ["mvn", "-v"]
