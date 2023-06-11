#!/bin/bash -e

pushd /mnt/vm2/docker/volumes/yuzu_data/_data
source ~/yuzu-nintendo-switch-emulator/steam-deck-gcc-12-build-flags.sh

# To setup this git clone, run:
# 1. git clone --recursive https://github.com/yuzu-emu/yuzu ./
#     The "./" at the end is important to make the path correct
#     for docker volume mounting.
# 2. git config --global --add safe.directory /mnt/vm2/docker/volumes/yuzu_data/_data
set -x
git checkout master --force
git restore .
git clean --force --force -d --exclude=ccache/ --exclude=artifacts/
git reset --hard
git fetch
git --no-pager diff origin/master --shortstat
git pull --verbose
git submodule update --init --recursive --force
set +x

perl -pi -w -e \
    's/^(.*DCMAKE_CXX_FLAGS.*)$/      -DCMAKE_CXX_FLAGS="'"${YUZU_COMPILE_FLAGS}"'" \\/g;' \
    .ci/scripts/linux/docker.sh

perl -pi -w -e \
    's/^(.*DUSE_DISCORD_PRESENCE.*)$/      -DUSE_DISCORD_PRESENCE=OFF \\/g;' \
    .ci/scripts/linux/docker.sh

perl -pi -w -e \
    's/^(.*DYUZU_ENABLE_COMPATIBILITY_REPORTING.*)$/      -DYUZU_ENABLE_COMPATIBILITY_REPORTING=OFF \\/g;' \
    .ci/scripts/linux/docker.sh


perl -pi -w -e \
    's/^.*(DYUZU_ENABLE_LTO.*)$/      -DYUZU_ENABLE_LTO=ON -DYUZU_TESTS=OFF \\/g;' \
    .ci/scripts/linux/docker.sh

set -x
docker run \
    -e CCACHE_DIR=/yuzu/ccache \
    -v "$(pwd):/yuzu" \
    -w /yuzu \
    yuzuemu/build-environments:linux-fresh \
    /bin/bash /yuzu/.ci/scripts/linux/docker.sh

docker run \
    -e CCACHE_DIR=/yuzu/ccache \
    -v "$(pwd):/yuzu" \
    -w /yuzu \
    yuzuemu/build-environments:linux-fresh \
    /bin/bash /yuzu/.ci/scripts/linux/upload.sh

scp \
    build/yuzu-*.AppImage \
    linux1:/home/hide/Personal_Directories/Chris/

popd
