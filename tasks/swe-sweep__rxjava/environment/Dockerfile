# Maximally-buggy RxJava, frozen at candidate anchor version v2.2.5.
#
# Built upstream by `pandora construct build-image -t rxjava@2.2.5`, which prepares the build
# context under data/tasks/rxjava/maxbug/2.2.5/context/: it exports the RxJava source tree
# at v2.2.5 FROM THE LOCAL CLONE (no GitHub access here) into ./rxjava, and copies this
# file in as ./Dockerfile.
#
# Why JDK 8: v2.2.5 ships a Gradle 4.3.1 wrapper, and Gradle 4.x refuses to run on a JVM
# newer than 10. The tree also compiles with `sourceCompatibility = 1.6`, which javac 9+
# has dropped, so 8 is the only version that satisfies both ends.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/reactivex/rxjava.git /src \
 && git -C /src checkout --quiet v2.2.5 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM docker.io/library/eclipse-temurin:8-jdk-jammy
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

# Neither the Gradle wrapper (which downloads the distribution) nor Gradle's own
# dependency resolution reads http_proxy — both are Java, and Java wants system
# properties. Translate the build-time proxy into the two places that do get read:
# GRADLE_OPTS for the wrapper's own JVM, and ~/.gradle/gradle.properties for the build.
RUN set -eux; \
    mkdir -p /root/.gradle; \
    : > /etc/profile.d/gradle-proxy.sh; \
    url="${http_proxy:-${HTTP_PROXY:-}}"; \
    if [ -n "$url" ]; then \
        host=$(echo "$url" | sed -E 's#^[a-z]+://##; s#:.*##; s#/.*##'); \
        port=$(echo "$url" | sed -E 's#^[a-z]+://[^:]*:##; s#/.*##'); \
        { \
          echo "systemProp.http.proxyHost=$host"; \
          echo "systemProp.http.proxyPort=$port"; \
          echo "systemProp.https.proxyHost=$host"; \
          echo "systemProp.https.proxyPort=$port"; \
          echo "systemProp.http.nonProxyHosts=localhost|127.0.0.1"; \
          echo "systemProp.https.nonProxyHosts=localhost|127.0.0.1"; \
        } >> /root/.gradle/gradle.properties; \
        echo "export GRADLE_OPTS=\"-Dhttp.proxyHost=$host -Dhttp.proxyPort=$port -Dhttps.proxyHost=$host -Dhttps.proxyPort=$port\"" > /etc/profile.d/gradle-proxy.sh; \
    fi

# Maven Central answers this proxy's shared identity with HTTP 429 under load, and Gradle
# does not retry a 429 — it fails the whole resolve. Put Google's read-only Maven Central
# mirror FIRST in every repository list so repo1.maven.org is never asked. `projectsLoaded`
# and `beforeProject` both run before a build.gradle is evaluated, so the mirror is ahead
# of whatever the buildscript adds, for the plugin classpath as well as the dependencies.
RUN set -eux; \
    mkdir -p /root/.gradle/init.d; \
    { \
      echo "def MIRROR = 'https://maven-central.storage-download.googleapis.com/maven2'"; \
      echo "gradle.projectsLoaded { g -> g.rootProject.buildscript.repositories.maven { url MIRROR } }"; \
      echo "gradle.beforeProject { p ->"; \
      echo "    p.buildscript.repositories.maven { url MIRROR }"; \
      echo "    p.repositories.maven { url MIRROR }"; \
      echo "}"; \
    } > /root/.gradle/init.d/central-mirror.gradle

# RxJava source tree at the candidate ref, exported from the local clone (see the header).
COPY --from=swesweep-src /src /rxjava
WORKDIR /rxjava

# Replace the project's build file with a minimal, test-only equivalent.
#
# RxJava's own build.gradle is mostly release machinery — bintray, artifactory, the OSGi
# jar manifest, javadoc, jmh, the license-header check, animalsniffer — and it resolves
# that plugin classpath from jcenter (shut down in 2021) and from plugins.gradle.org.
# Through this host's shared proxy those lookups come back HTTP 429, which Gradle does not
# retry, so the build cannot even be configured. None of it is needed to compile
# `src/main` and run `src/test`, which is all a census does.
#
# The dependency versions below are copied verbatim from v2.2.5's build.gradle, so the
# compile and test classpath is the period-correct one. `src/jmh` is dropped with the jmh
# plugin: it is a benchmark source set, not product code and not a test suite.
#
# This runs BEFORE the baseline commit on purpose: a subtask resets to `baseline`, so the
# replacement has to be part of it rather than a layer on top. Nothing is lost from the
# graded patches either — build.gradle matches neither source_globs nor test_globs, so
# `patching.split_diff` puts it in `other_files` and drops it from both.
RUN set -eux; \
    { \
      echo 'apply plugin: "java-library"'; \
      echo ''; \
      echo 'group = "io.reactivex.rxjava2"'; \
      echo 'version = "2.2.5"'; \
      echo ''; \
      echo 'sourceCompatibility = JavaVersion.VERSION_1_8'; \
      echo 'targetCompatibility = JavaVersion.VERSION_1_8'; \
      echo ''; \
      echo 'repositories {'; \
      echo '  maven { url "https://maven-central.storage-download.googleapis.com/maven2" }'; \
      echo '  mavenCentral()'; \
      echo '}'; \
      echo ''; \
      echo 'dependencies {'; \
      echo '    api "org.reactivestreams:reactive-streams:1.0.2"'; \
      echo '    testImplementation "junit:junit:4.12"'; \
      echo '    testImplementation "org.mockito:mockito-core:2.1.0"'; \
      echo '    testImplementation "org.reactivestreams:reactive-streams-tck:1.0.2"'; \
      echo '    testImplementation "org.testng:testng:6.11"'; \
      echo '    testImplementation "com.google.guava:guava:24.0-jre"'; \
      echo '}'; \
      echo ''; \
      echo 'test {'; \
      echo '    maxHeapSize = "2g"'; \
      echo '    testLogging { exceptionFormat = "full" }'; \
      echo '}'; \
    } > build.gradle

# Make the exported tree a git repo (the export carries no .git), commit the source and
# tag it `baseline`. `build/` and `.gradle/` are in RxJava's own .gitignore, so the warm
# build below is not part of the baseline commit and a subtask's
# `git reset --hard baseline && git clean -fdq` (no -x) leaves it in place.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "rxjava maxbug source" && git tag baseline

# Warm the build: download the Gradle distribution, resolve the whole compile and test
# dependency graph into ~/.gradle, and compile main + test. This is what makes a subtask's
# rebuild an incremental recompile rather than a cold resolve, and it is what lets the
# census run with `--offline`.
#
RUN set -eux; \
    . /etc/profile.d/gradle-proxy.sh 2>/dev/null || true; \
    for attempt in 1 2 3 4 5; do \
        ./gradlew --no-daemon testClasses && exit 0; \
        sleep 60; \
    done; \
    echo "gradle could not compile the test source set in 5 attempts" >&2; exit 1

# Run one small test class so the test runtime (JUnit, mockito, guava, testng) is resolved
# and cached too — a census run is offline and cannot fetch it later.
RUN set -eux; \
    . /etc/profile.d/gradle-proxy.sh 2>/dev/null || true; \
    ./gradlew --no-daemon test --tests 'io.reactivex.internal.util.ExceptionHelperTest*' \
    || ./gradlew --no-daemon test --tests 'io.reactivex.*ExceptionHelperTest*'

CMD ["./gradlew", "--version"]
