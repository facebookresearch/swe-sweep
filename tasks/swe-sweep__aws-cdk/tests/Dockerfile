# Maximally-buggy aws-cdk — frozen at anchor version 1.94.1.
#
# Built upstream by `pandora construct build-image -t aws-cdk@1.94.1`, which prepares the build context
# from the local clone (no GitHub access — see docs/ai/010-design/005-style-conventions.md):
# it exports the source tree at v1.94.1 into ./aws-cdk and copies this file in as
# ./Dockerfile. The image holds the tree with a `baseline` commit+tag; the in-container
# validator (tasks/aws-cdk/task.yaml) does `git reset --hard baseline`, then applies
# the per-bug test/gold patches.
#
# Why v1: the v1→v2 move merged every `@aws-cdk/aws-*` package into one `aws-cdk-lib`, so a
# patch written against the v1 layout cannot apply to v2 and vice versa. Both patches apply
# for 176 subtasks at v1.94.1, against 164 at v2.100.0, 144 at v2.0.0 and 103 at v2.150.0 —
# and the v1 peak is also where the coverage curve peaks. See
# docs/ai/040-experiments/aws-cdk/260819-anchor-choice.md.
#
# Why Node 14: v1.94 (March 2021) is built and tested on Node 10/12/14, and jsii's compiler
# of that era does not run on Node 18+.
# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/aws/aws-cdk.git /src \
 && git -C /src checkout --quiet v1.94.1 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

FROM docker.io/library/alpine:3.20 AS swesweep-python
RUN apk add --no-cache curl \
 && curl -fsSL -o /pbs.tgz "https://github.com/astral-sh/python-build-standalone/releases/download/20260924/cpython-3.12.14%2B20260924-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz" \
 && echo "269b2c99e4db15b242bf01832f4fea1e8f1a664f273cff519393f296e9820b41  /pbs.tgz" | sha256sum -c - \
 && mkdir -p /opt/swesweep && tar -xzf /pbs.tgz -C /opt/swesweep && rm /pbs.tgz

# --- upstream Dockerfile, unchanged below ---
FROM node:14-bullseye
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

# git supports host-directed reset/apply. Python remains available for package build tools.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends git ca-certificates python3; \
    ln -sf /usr/bin/python3 /usr/local/bin/python; \
    rm -rf /var/lib/apt/lists/*

# Host-driven evaluation supplies complete commands, so do not let the base image prepend `node`.
ENTRYPOINT []

COPY --from=swesweep-src /src /aws-cdk
WORKDIR /aws-cdk

# The monorepo is yarn-1 workspaces. `--frozen-lockfile` is what makes the install
# period-correct: the committed yarn.lock decides every version, not today's registry.
# `--network-timeout` because this install pulls ~2GB through the proxy and yarn's default
# 30s timeout gives up on the slowest tarballs.
RUN yarn install --frozen-lockfile --network-timeout 600000

# A frozen tree does not stay lint-clean as the calendar moves. Each package's build runs
# `pkglint`, whose `license/notice-file` rule requires every NOTICE to begin with the
# copyright range ending in **the current year** — so a 2021 tree fails in 2026 with
# "NOTICE does NOT begin with … Copyright 2018-2026".
#
# `pkglint --fix` cannot repair it: `fileShouldBeginWith` (tools/pkglint/lib/util.ts) reports
# the violation with no `fix` callback, unlike every neighbouring rule. So the second line of
# each NOTICE is rewritten here instead — the exact string the rule builds from
# `new Date().getFullYear()`, and nothing else in the file.
#
# The sibling `license/license-file` rule wants the same year inside the Apache appendix of
# every LICENSE, so both files get the same one-line rewrite.
#
# NOTICE and LICENSE match neither `source_globs` nor `test_globs`, so they land in
# `other_files` and are dropped from both patches: this can never collide with a subtask's
# gold or test patch.
RUN Y=$(date +%Y); \
    C="Copyright 2018-$Y Amazon.com, Inc. or its affiliates. All Rights Reserved."; \
    find . -name NOTICE -not -path '*/node_modules/*' -exec \
        sed -i "2{/^Copyright 2018-/s|.*|$C|}" {} + ; \
    find . -name LICENSE -not -path '*/node_modules/*' -exec \
        sed -i "s|^   Copyright 2018-[0-9]* Amazon\.com, Inc\. or its affiliates\. All Rights Reserved\.$|   $C|" {} +

# Compile every package. aws-cdk's tests import the *built* `lib/*.js` of the packages they
# depend on, not their TypeScript, so an unbuilt tree fails every test with an unresolved
# import rather than with the bug under test. The three `--skip-*` keep this to the compile:
# the suites themselves are what the census runs, one subtask at a time, and the compat check
# fetches the previously published API surface from npm to diff the built one against.
#
# `--no-bail` because the reactor contains tooling packages that are not library code and
# do not build here — `awslint` is aws-cdk's own API-style linter, and nothing under test
# imports it. Bailing on the first such package leaves the other 213 uncompiled.
#
# NODE_OPTIONS raises the heap — the default is far too small for a 200-package tsc run and
# the build dies with an out-of-memory abort halfway through.
ENV NODE_OPTIONS=--max-old-space-size=8192

# The workspace's hoisted binaries have to be on PATH for the whole build. `yarn run` puts
# them there, but the reactor is driven with `npm run` in places (and directly here), and
# npm only adds the *package's* own node_modules/.bin — so a package's `gen` script that
# calls a bare `tsc` or `cfn2ts` dies with "command not found" and the build carries on
# past it.
ENV PATH=/aws-cdk/node_modules/.bin:$PATH

# **The build tools go first, with plain tsc.** `build.sh` drives every package through
# `cdk-build`, and `cdk-build` is itself TypeScript under `tools/cdk-build-tools/bin` — so
# until the tools are compiled, *every* package's build fails on the first line and the
# whole reactor falls through to the tsc sweep below. That is the state this image shipped
# in: no package ever ran its real build.
#
# jsii is not used here on purpose. These are plain node programs, not jsii libraries, and
# `tsc -p` builds all of them cleanly with no cross-package cycle to work around.
RUN set -eux; \
    for p in tools/cdk-build-tools tools/pkglint tools/cfn2ts tools/nodeunit-shim \
             tools/eslint-plugin-cdk tools/pkgtools tools/cdk-integ-tools tools/yarn-cling; do \
        [ -f "$p/tsconfig.json" ] || continue; \
        echo "== tools $p"; \
        (cd "$p" && tsc -p tsconfig.json) || true; \
    done; \
    test -f tools/cfn2ts/lib/index.js; \
    test -f tools/cdk-build-tools/bin/cdk-build.js

# **Then the CloudFormation spec, then `gen` everywhere.** Every service package's L1
# constructs — `lib/<service>.generated.ts`, the `CfnBucket`-style classes the whole library
# is built on — are *not* committed: `cfn2ts` writes them from `@aws-cdk/cfnspec`, whose own
# `spec/specification.json` is in turn assembled from `spec-source/` by its build script.
#
# Neither ran in this image before, so no package had any generated source, and every test
# died at import time on `Cannot find module './<service>.generated'` — one collection error
# in both states, which reads as "the test fails before *and* after the fix" and cost the
# census all but one of its 458 applying subtasks.
#
# `npm run gen`, not `cfn2ts` directly: three packages generate something else (region-info
# compiles a data generator, custom-resources copies the SDK's api metadata, events-targets
# runs its own script), and the package script is the only thing that knows which.
RUN set -eux; \
    (cd packages/@aws-cdk/cfnspec && tsc -p tsconfig.json || true) \
    && (cd packages/@aws-cdk/cfnspec && node build-tools/build) \
    && test -f packages/@aws-cdk/cfnspec/spec/specification.json
RUN set -eux; \
    for d in $(ls -d packages/@aws-cdk/*/ packages/*/ 2>/dev/null); do \
        p="${d%/}"; \
        [ -f "$p/package.json" ] || continue; \
        node -e "var s=require('/aws-cdk/$p/package.json').scripts||{};process.exit(s.gen?0:1)" \
            || continue; \
        echo "== gen $p"; \
        (cd "$p" && npm run gen) || echo "gen failed: $p"; \
    done; \
    test -f packages/@aws-cdk/aws-s3/lib/s3.generated.ts

# 21 of the 214 packages cannot finish this build, and re-running does not help: the cycle is
# real. jsii compiles `test/` along with `lib/` and then refuses to emit *anything* when any
# file in the program has a type error — so a cycle that exists only between one package's
# tests and another package's library costs that library its JavaScript. Those 21 include
# `aws-stepfunctions-tasks`, this anchor's most-touched package (42 subtasks), so leaving them
# unbuilt is not an option.
#
# **The integ files go first**, before the build rather than after it — most of the cycle runs
# through `test/**/integ.*.ts`, deployment scripts that stand up real AWS resources and that
# this census can never run. They match `test_globs`, so they are already excluded from every
# gold patch; exactly one of the 176 applying subtasks has a test patch that touches nothing
# else, and it loses its verdict.
RUN find packages -path '*/test/*' -name 'integ.*.ts' -delete

# **Three passes.** aws-cdk's packages depend on each other through their *tests* as well as
# their libraries, and those edges make cycles that lerna's topological order cannot satisfy
# in one sweep: a package whose dependency has not been built yet fails with
# `Cannot find module '@aws-cdk/...'`. Each pass builds the ones whose dependencies the
# previous pass produced — 85 packages fail on the first pass, 21 after the second, and the
# third is what settles it. `--no-bail` keeps a pass going past its failures.
RUN for pass in 1 2 3; do \
        echo "== build pass $pass"; \
        ./build.sh --skip-test --skip-prereqs --skip-compat --no-bail && break; \
    done; true

# **Then tsc wherever jsii still gave up.** Plain tsc emits JavaScript for the files that are
# fine while still reporting TS2307 for the ones that are not — the behaviour jsii
# deliberately suppresses. jsii is re-run first only to regenerate the `tsconfig.json` it
# removes on failure; its exit code is ignored, as is tsc's, and the guard below is what
# decides whether any of this worked.
#
# Absolute paths to both binaries, not `npx --no-install`: npx resolves against the *package's*
# node_modules, and these are hoisted to the workspace root, so npx answers `not found: jsii`
# and the whole sweep silently does nothing.
#
# jsii also refuses to start when a *dependency's* `.jsii` assembly is missing, and then it
# writes no tsconfig at all — so the fallback writes one. aws-cdk packages all have the same
# shape (TypeScript under `lib/` and `test/`, emitted beside itself), which is what makes a
# generic tsconfig correct here rather than a guess.
#
# `test/**/*.ts` is in the `include` deliberately: aws-cdk's jest config matches `*.test.js`,
# so a package whose tests are never transpiled has no tests at all as far as the census is
# concerned, and every one of its subtasks reports zero collected in both states.
#
# "Already built" means *every* TypeScript file under `lib/` has its JavaScript, not just
# `lib/index.js`. A package whose L1 constructs were generated after its last successful
# compile has an index but no `<service>.generated.js`, and that single missing file takes
# down every test that imports the package.
RUN set -eux; \
    for p in $(ls -d packages/*/ packages/@*/*/ 2>/dev/null); do \
        [ -f "$p/package.json" ] || continue; \
        [ -d "$p/lib" ] || continue; \
        if [ -f "$p/lib/index.js" ] \
           && ! find "$p/lib" -name '*.ts' -not -name '*.d.ts' \
                  -exec sh -c '[ ! -f "${1%.ts}.js" ]' _ {} \; -print | grep -q .; then \
            continue; \
        fi; \
        echo "== sweep $p"; \
        (cd "$p" && /aws-cdk/node_modules/.bin/jsii --silence-warnings=reserved-word) || true; \
        if [ ! -f "$p/tsconfig.json" ]; then \
            printf '%s' '{"compilerOptions":{"target":"ES2018","module":"commonjs","lib":["es2018"],"declaration":true,"strict":false,"noEmitOnError":false,"skipLibCheck":true,"esModuleInterop":false,"resolveJsonModule":true,"experimentalDecorators":true},"include":["lib/**/*.ts","test/**/*.ts"]}' \
                > "$p/tsconfig.json"; \
        fi; \
        (cd "$p" && /aws-cdk/node_modules/.bin/tsc -p tsconfig.json) || true; \
    done

# Fail the build if the packages the population actually needs still have no JavaScript.
# Without this the tsc sweep could silently do nothing and every subtask would come back as a
# build failure instead of as a bug.
#
# The generated half is checked separately, and `cx-api` by name: those were the two files
# whose absence produced 430 "fails before and after the fix" verdicts, and neither is
# visible in an `lib/index.js` check.
RUN set -eux; \
    for p in aws-stepfunctions-tasks aws-lambda aws-stepfunctions aws-codepipeline-actions \
             core cx-api aws-ec2 aws-s3 aws-apigatewayv2; do \
        test -f "packages/@aws-cdk/$p/lib/index.js" \
            || { echo "packages/@aws-cdk/$p has no built lib/index.js" >&2; exit 1; }; \
    done; \
    for p in aws-s3 aws-lambda aws-ec2 aws-apigatewayv2 aws-stepfunctions; do \
        ls "packages/@aws-cdk/$p"/lib/*.generated.js >/dev/null \
            || { echo "packages/@aws-cdk/$p has no compiled L1 constructs" >&2; exit 1; }; \
    done

RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "aws-cdk maxbug source" && git tag baseline

CMD ["node", "-e", "console.log('aws-cdk', require('/aws-cdk/packages/aws-cdk/package.json').version)"]

# --- SWE-sweep Harbor port: the sandbox idles; the harness execs into it ---
ENTRYPOINT []
CMD ["sleep", "infinity"]
# --- SWE-sweep verifier: the evaluator's interpreter and the test fixture ---
COPY --from=swesweep-python /opt/swesweep/python /opt/swesweep/python
COPY . /tests
RUN chmod +x /tests/test.sh
