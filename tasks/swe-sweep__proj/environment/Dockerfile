# Maximally-buggy proj — one recipe for every 6.x anchor candidate (6.0.0, 6.2.0,
# 6.3.0). They span ten months of one major version and share a build system, a
# dependency set and a test layout, so they share a Dockerfile.
#
# Built upstream by `pandora construct build-image -t proj@<v>`, which prepares the build context
# under data/tasks/proj/maxbug/<v>/context/: it exports the proj source tree at <v> FROM
# THE LOCAL CLONE (no GitHub access — see docs/ai/010-design/005-style-conventions.md)
# into ./proj, and copies this file in as ./Dockerfile. The image holds the proj git tree
# with a `baseline` commit+tag; the host-controlled evaluator
# (tasks/proj/task.yaml) does `git reset --hard baseline`, then applies the
# per-bug test/gold patches.
#
# The build tree lives at /build, **outside** the repository, so the runner's
# `git clean -fdq` between instances cannot delete it and every per-subtask rebuild is
# incremental.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/OSGeo/PROJ.git /src \
 && git -C /src checkout --quiet 6.3.0 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM debian:bullseye-slim
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# git is needed in-container to reset/apply/clean between instances. sqlite3 is needed
# *twice*: the library PROJ links against, and the command-line tool, which PROJ's build
# shells out to in order to assemble `proj.db` from the SQL under `data/`. cmake's
# configure step hard-errors if it cannot find the binary.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        git ca-certificates build-essential cmake \
        sqlite3 libsqlite3-dev; \
    rm -rf /var/lib/apt/lists/*

# PROJ finds its resource files — `proj.db` above all — through $PROJ_LIB, falling back
# to a path baked in at install time. Nothing is installed here, so without this every
# test that resolves a CRS fails at the point of opening the database. The build writes
# `proj.db` and the dictionary files into the `data/` subdirectory of the build tree.
ENV PROJ_LIB=/build/data

# proj source tree at the anchor ref, exported from the local clone into the build
# context (see the header).
COPY --from=swesweep-src /src /proj
WORKDIR /proj

# Make the exported tree a git repo (the export carries no .git), commit the *source*
# and tag it `baseline`, then configure and build. Committing first keeps the baseline
# source-only: everything the compiler produces lands in /build.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "proj maxbug source" && git tag baseline

# The unit tests are gtest, and PROJ 6 vendors it *by download*: the configure step
# fetches the googletest 1.8.1 release archive and adds it to the build. That is the only
# step in this image that needs the network beyond apt, and it happens here, at build
# time — the suite never re-configures, so no later run depends on it.
RUN cmake -S /proj -B /build \
        -DCMAKE_BUILD_TYPE=Release \
    && cmake --build /build -j "$(nproc)"

CMD ["/build/bin/proj_test_cpp_api", "--gtest_list_tests"]
