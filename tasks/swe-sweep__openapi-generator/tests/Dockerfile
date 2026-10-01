# Maximally-buggy openapi-generator — the 7.x anchors.
#
# Built upstream by `pandora construct build-image -t openapi-generator@<v>`, which prepares the
# build context under data/tasks/openapi-generator/_local_only/maxbug/<v>/context/: it
# exports the source tree at the anchor tag FROM THE LOCAL CLONE (no GitHub access — see
# docs/ai/010-design/005-style-conventions.md) into ./openapi-generator, and copies this
# file in as ./Dockerfile.
#
# One Dockerfile for the whole 7.x line: every 7.x release sets
# `maven.compiler.source/target` to 11, so they all want the same JDK. A 5.x or 6.x
# anchor would need its own file.
#
# Only the tool's own modules are built. The `openapi-generator` profile is
# `activeByDefault` and names six of them; every other module in the root pom is a
# checked-in *sample* behind an opt-in profile — thousands of generated projects in a
# dozen languages, none of them graded and none of them buildable without their own
# toolchains.
#
# Five of those six are built, not all six. `openapi-generator-gradle-plugin` is a maven
# *wrapper* around a gradle build: its one goal downloads a Gradle distribution from
# services.gradle.org and runs it, which no build host here can reach and no offline
# reproduction run could repeat anyway. Its subtasks report "no targets" instead.

# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/OpenAPITools/openapi-generator.git /src \
 && git -C /src checkout --quiet v7.2.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM docker.io/library/maven:3.9.6-eclipse-temurin-11
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

# Maven's network configuration: a mirror that Meta's FwdProxy will serve, plus the proxy
# itself when the build host has one.
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

COPY --from=swesweep-src /src /openapi-generator
WORKDIR /openapi-generator

# Make the exported tree a git repo (the export carries no .git), commit the sources and
# tag them `baseline` — a SOURCE-ONLY tag. The repo's own .gitignore covers `target/`, so
# the runner's `git reset --hard baseline && git clean -fdq` (no -x) resets the sources
# between subtasks while keeping the compiled output below.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "openapi-generator maxbug source" && git tag baseline

# One connection at a time, and retried: maven's default five parallel downloads trip
# Meta's FwdProxy rate limit within seconds (HTTP 429 on CONNECT). Serialized and retried
# the same fetch goes through — and because maven resumes from what is already in ~/.m2,
# each attempt starts where the last stopped.
ENV MAVEN_FETCH="-Dmaven.artifact.threads=1 -Dmaven.wagon.http.retryHandler.count=10 \
-Dmaven.wagon.http.retryHandler.requestSentEnabled=true -Dmaven.wagon.rto=120000"
ENV MAVEN_OPTS="-Xmx4g"
ENV SKIPS="-DskipTests -Dmaven.javadoc.skip=true -Dmaven.source.skip=true \
-Denforcer.skip=true -Dlicense.skip=true -Dgpg.skip=true"

ENV MODULES="modules/openapi-generator-core,modules/openapi-generator,modules/openapi-generator-cli,modules/openapi-generator-maven-plugin,modules/openapi-generator-online"

# Warm ~/.m2 and target/: install the tool's own modules. This is what lets a reproduction
# run stay OFFLINE (`mvn -o`) and still recompile the module a patch changed.
RUN for attempt in 1 2 3 4 5 6; do \
        echo "== install attempt $attempt"; \
        mvn -B -pl "$MODULES" -am $SKIPS $MAVEN_FETCH install && exit 0; \
        sleep 60; \
    done; \
    echo "maven could not install the reactor in 6 attempts" >&2; exit 1

# Warm the *test* half too, across every module the runner can select. Compiling the
# suites and running one real test is what pulls in surefire's **TestNG** provider and
# the test-scope dependencies; an offline reproduction run cannot fetch them, and the
# provider is not a dependency of the `install` above, so skipping this step fails every
# subtask with "surefire-testng ... has not been downloaded".
RUN for attempt in 1 2 3; do \
        mvn -B -pl "$MODULES" -am \
          -Dmaven.javadoc.skip=true -Dmaven.source.skip=true -Denforcer.skip=true \
          -Dlicense.skip=true $MAVEN_FETCH \
          -Dtest=DefaultCodegenTest -DfailIfNoTests=false \
          -Dsurefire.failIfNoSpecifiedTests=false test && exit 0; \
        sleep 60; \
    done; \
    echo "maven could not warm the test dependencies" >&2; exit 1

CMD ["mvn", "-v"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
