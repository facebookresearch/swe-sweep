# Maximally-buggy matplotlib — the 3.3/3.4 anchors.
#
# Python 3.8: 3.3.4 supports 3.6–3.9 and 3.4.3 supports 3.7–3.10, and the pinned
# scientific stack below is the one both were released against. The version floors are
# not decoration — matplotlib's own CI pins numpy and pillow because a newer numpy
# changes repr and casting rules, and half of matplotlib's suite asserts on rendered
# output.
#
# **The image builds matplotlib's own FreeType, not the system one.** That is the default
# (`system_freetype = False`), and it has to stay the default: the image-comparison tests
# are byte-level PNG diffs against baselines rendered with FreeType 2.6.1, and linking a
# distro FreeType shifts glyph rasterisation enough to fail hundreds of them. The build
# downloads and compiles it, which is why this image needs network at build time and none
# afterwards.

# --- SWE-sweep Harbor port: source trees come from clone stages ---
FROM docker.io/library/alpine:3.20 AS swesweep-src
RUN apk add --no-cache git
RUN set -eu \
 && git clone --quiet --no-checkout https://github.com/matplotlib/matplotlib.git /src \
 && git -C /src checkout --quiet v3.4.3 \
 && git -C /src submodule update --init --recursive --quiet \
 && echo "swesweep-src: $(git -C /src rev-parse HEAD)" \
 && find /src -name .git -prune -exec rm -rf {} +

# --- upstream Dockerfile, unchanged below ---
FROM docker.io/library/python:3.8-bullseye
# --- SWE-sweep Harbor port: apt repositories of EOL Debian suites ---
RUN if [ -r /etc/os-release ]; then . /etc/os-release; case "${VERSION_CODENAME:-}" in \
      stretch|buster) [ -f /etc/apt/sources.list ] && sed -i -e 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g' -e 's|http://security.debian.org/debian-security|http://archive.debian.org/debian-security|g' -e 's|http://security.debian.org|http://archive.debian.org/debian-security|g' -e '/-updates/d' /etc/apt/sources.list; printf 'Acquire::Check-Valid-Until "false";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
      bullseye) if [ -f /etc/apt/sources.list ] && grep -q '^# deb http://snapshot.debian.org' /etc/apt/sources.list; then sed -i -e '\|^# deb http://snapshot.debian.org.* bullseye main$|!s|^# deb http://snapshot.debian.org|deb http://snapshot.debian.org|' -e '\|^deb http://deb.debian.org/debian bullseye main$|!{\|^deb http://deb.debian.org|d}' /etc/apt/sources.list; elif [ -f /etc/apt/sources.list ]; then sed -i -e '/bullseye-security/d' -e '/bullseye-updates/d' /etc/apt/sources.list; fi; printf 'Acquire::Check-Valid-Until "false";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99swesweep-eol ;; \
    esac; fi

RUN set -eux; \
    echo 'APT::Sandbox::User "root";' >> /etc/apt/apt.conf.d/10sandbox; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        build-essential git ca-certificates pkg-config \
        libpng-dev libjpeg-dev zlib1g-dev \
        ghostscript inkscape texlive-latex-base texlive-latex-extra \
        texlive-fonts-recommended texlive-xetex texlive-luatex dvipng cm-super \
        fonts-freefont-otf fonts-humor-sans; \
    rm -rf /var/lib/apt/lists/*

COPY --from=swesweep-src /src /matplotlib
WORKDIR /matplotlib

# The export carries no `.git`; make one and tag the sources `baseline` so the runner can
# `git reset --hard baseline && git clean -fdq` between subtasks. `.gitignore` covers
# `build/` and the generated `lib/matplotlib/_version.py`, so the compiled extensions
# below survive the reset and a subtask's rebuild is incremental.
RUN git init -q \
    && git config user.email v@x && git config user.name v \
    && git add -A && git commit -q -m "matplotlib maxbug source" && git tag baseline

# matplotlib is versioned by `versioneer`, which reads the tag. A source export has none
# of the repo's real tags, so pin the version rather than let it resolve to 0+unknown.
ENV SETUPTOOLS_SCM_PRETEND_VERSION=3.4.3

# The runtime stack, pinned to the era. `pytest<7` because matplotlib 3.3's conftest uses
# the old `pytest.Item` API, and `pikepdf<3` because 3.x needs Python 3.7+ *and* a newer
# qpdf than bullseye ships.
RUN python -m pip install --no-cache-dir --upgrade "pip<24" "setuptools<60" wheel \
    && python -m pip install --no-cache-dir \
        "numpy==1.20.3" "pillow==8.3.2" "cycler==0.10.0" "kiwisolver==1.3.1" \
        "pyparsing==2.4.7" "python-dateutil==2.8.2" "certifi" \
        "pytest==6.2.5" "pytest-timeout" "pytest-xdist" "pytest-rerunfailures" \
        "tornado==6.1" "pytz==2021.1" "pandas==1.3.5" "pikepdf==2.16.1" \
        "ipython==7.31.1" "ipykernel==6.9.1" "nbformat==5.1.3" "nbconvert==6.4.2" \
        "psutil"

# Editable, so a subtask's `git reset` puts the patched Python back in the import path
# with no reinstall — only the C extensions need rebuilding, which is what the runner's
# build command does.
RUN python -m pip install --no-cache-dir --no-build-isolation -e .

# Every backend that needs a display is out of scope; Agg is what the suite renders with.
ENV MPLBACKEND=Agg
# A writable, per-container cache: matplotlib builds its font list on first import, and a
# read-only or shared HOME turns that into a warning on every single test.
ENV MPLCONFIGDIR=/tmp/mplconfig

CMD ["python", "-c", "import matplotlib; print(matplotlib.__version__)"]
