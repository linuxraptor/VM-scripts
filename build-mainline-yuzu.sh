#!/bin/bash -e

# BEFORE RUNNING THIS SCRIPT:
# This docker build requires a recursive permissions change to the docker
# volume files so that the user inside the docker container has correct
# execution permissions. This causes the build, and this script, to be
# inherently brittle.
#
# Expect permission fuckery for this volume.
#
# Take note of ownership of the docker volume, or the volume might need to be
# replaced regularly.

YUZU_VOLUME_NAME="yuzu_data"
GCC_FLAGS_SRC="$(readlink -f ./steam-deck-gcc-12-build-flags.sh)"

# To DELETE the docker container:
# (inspired by https://docs.tibco.com/pub/mash-local/4.3.0/doc/html/docker/GUID-BD850566-5B79-4915-987E-430FC38DAAE4.html)
# 1. docker rm -f $(docker ps -a | grep yuzuemu/build-environments:linux-fresh | awk '{print $1}')
# 2. docker volume rm "${YUZU_VOLUME_NAME}"
# 3. docker image ls -a  # remove leftover images with `docker image rm ...`
# 4. docker volume ls
#    # docker volume prune might be a good idea after this.

# To CREATE the docker congtainer:
# 1. docker volume create "${YUZU_VOLUME_NAME}"
# 2. YUZU_DOCKER_VOLUME_DIR="$(docker volume inspect ${YUZU_VOLUME_NAME} | grep Mountpoint | cut -d'"' -f 4)"
# 3. cd "${YUZU_DOCKER_VOLUME_DIR}"
# 4. git clone --depth 1 --recursive https://github.com/yuzu-emu/yuzu-mainline ./
#    #  The "./" at the end is important to make the path correct for docker volume mounting.
#    #  Consider if 'yuzu-mainline' is the correct repository to clone.
#    #  Despite the --depth flag, recursive submodules will not be shallow:
#    #  https://stackoverflow.com/questions/2144406/how-to-make-shallow-git-submodules/47374702#47374702

# To build after a reset, just run this script.
# The docker pull and run commands are already here.

# There are clues to sync to git-mainline here:
# https://dev.azure.com/yuzu-emu/yuzu/_build/results?buildId=23546&view=logs&j=b457fee1-24b5-5b05-276f-95f55538c81f&t=4cc2ca70-e134-5e5c-cfa3-3f582a967df4

# Can be "mainline" or "early-access".
# Changing the release name will change the build target,
# as long as the correct github repo is cloned during setup.
# Mainline is the github-released build.
# early-access is like a nightly build.
RELEASE_CHANNEL="mainline"

YUZU_DOCKER_VOLUME_DIR="$(docker volume inspect ${YUZU_VOLUME_NAME} | grep Mountpoint | cut -d'"' -f 4)"

pushd "${YUZU_DOCKER_VOLUME_DIR}"
source "${GCC_FLAGS_SRC}"

echo "Running Git commands."
set -x
git checkout master --force
git restore .
git clean --force --force -d --exclude=ccache/ --exclude=artifacts/
git reset --hard
git fetch --depth=1
git --no-pager diff origin/master --shortstat
git pull --depth=1 --verbose
git submodule update --init --recursive --force


if [[ "${RELEASE_CHANNEL}" == "mainline" ]]; then
    RELEASE_NUM="$(git tag --points-at HEAD | sed -r 's/^.+-([0-9]+)$/\1/')"
fi
# The below commands taken from:
# https://github.com/yuzu-emu/yuzu/blob/master/.ci/scripts/linux/exec.sh
mkdir -p ccache || true
chmod a+x ./.ci/scripts/linux/docker.sh
# Git requires permissions on the host system to reflect a known user.
VOL_OWNER_ID=$(stat --format="%u" .)
# But docker requires permissions inside the volume to be uid=1027.
sudo chown -R 1027 ./
set +x

echo "Running GCC flag replacements"
perl -pi -w -e \
    's/^(.*DCMAKE_CXX_FLAGS.*)$/      -DCMAKE_CXX_FLAGS="'"${YUZU_COMPILE_FLAGS}"'" \\/g;' \
    .ci/scripts/linux/docker.sh

# We cannot guarantee stability between our custom GCC flags and Yuzu tests.
perl -pi -w -e \
    's/^.*(DYUZU_ENABLE_LTO.*)$/      -DYUZU_ENABLE_LTO=ON -DYUZU_TESTS=OFF \\/g;' \
    .ci/scripts/linux/docker.sh

echo "Running Docker pull."
docker pull yuzuemu/build-environments:linux-fresh
set -x

echo "Building in container."
# https://github.com/yuzu-emu/yuzu/blob/master/.ci/scripts/linux/docker.sh
docker run \
    -e CCACHE_DIR=/yuzu/ccache \
    -v "$(pwd):/yuzu" \
    -w /yuzu \
    yuzuemu/build-environments:linux-fresh \
    /bin/bash /yuzu/.ci/scripts/linux/docker.sh "${RELEASE_NUM}"

echo "Packaging in container."
# https://github.com/yuzu-emu/yuzu/blob/master/.ci/scripts/linux/upload.sh
docker run \
    -e CCACHE_DIR=/yuzu/ccache \
    -e RELEASE_NAME="${RELEASE_CHANNEL}" \
    -v "$(pwd):/yuzu" \
    -w /yuzu \
    yuzuemu/build-environments:linux-fresh \
    /bin/bash /yuzu/.ci/scripts/linux/upload.sh

# Reverting permissions to (hopefully) before script execution.
sudo chown -R ${VOL_OWNER_ID} ./

pushd build
NEWBUILD=$(ls -t1A --color=never *.AppImage | head -n 1)
if [[ "${RELEASE_CHANNEL}" == "mainline" ]]; then
    MAINLINE_BUILD="yuzu-mainline-${RELEASE_NUM}.AppImage"
    mv "${NEWBUILD}" "${MAINLINE_BUILD}"
    NEWBUILD="${MAINLINE_BUILD}"
fi
echo -e "\n\nNew build located here:"
readlink -f "${NEWBUILD}"

# If you'd like to copy $NEWBUILD to a more convenient location,
# this would be an ideal place to do it.

popd  # build
popd  # YUZU_DOCKER_VOLUME_DIR
