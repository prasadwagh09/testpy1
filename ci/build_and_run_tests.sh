#!/bin/bash

# Usage
# build_and_run_tests.sh <workspace> [-b <bazel path>] [--env pip|conda] [--mode merge_gate|continuous_run|release] [--with-snowpark]
#
# Args
# workspace: path to the workspace, SnowML code should be in snowml directory.
#
# Optional Args
# b: specify path to bazel
# env: Set the environment, choose from pip and conda
# mode: Set the tests set to be run.
#   merge_gate: run affected tests only.
#   continuous_run (default): run all tests except auto-generated tests. (For nightly run.)
#   release: run all tests including auto-generated tests. (For releasing)
# with-snowpark: Build and test with snowpark in snowpark-python directory in the workspace.
#
# Action
#   - Copy the integration tests from workspace folder and execute them in testing Python env using pytest.
#   - This is to mimic the behavior of using snowml wheel package in user land.

set -o pipefail
set -u
set -e

PROG=$0

help() {
    local exit_code=$1
    echo "Usage: ${PROG} <workspace> [-b <bazel path>] [--env pip|conda] [--mode merge_gate|continuous_run|release] [--with-snowpark]"
    exit "${exit_code}"
}

WORKSPACE=$1 && shift || help 1
BAZEL="bazel"
ENV="pip"
WITH_SNOWPARK=false
MODE="continuous_run"
SNOWML_DIR="snowml"
SNOWPARK_DIR="snowpark-python"
IS_NT=false

while (($#)); do
    case $1 in
    -b | --bazel_path)
        shift
        BAZEL=$1
        ;;
    -e | --env)
        shift
        if [[ $1 = "pip" || $1 = "conda" ]]; then
            ENV=$1
        else
            help 1
        fi
        ;;
    --with-snowpark)
        WITH_SNOWPARK=true
        ;;
    --mode)
        shift
        if [[ $1 = "merge_gate" || $1 = "continuous_run" || $1 = "release" ]]; then
            MODE=$1
        else
            help 1
        fi
        ;;
    -h | --help)
        help 0
        ;;
    *)
        help 1
        ;;
    esac
    shift
done

EXT=""
BAZEL_ADDITIONAL_BUILD_FLAGS=()
BAZEL_ADDITIONAL_STARTUP_FLAGS=()

# Computing artifact location
# Detect the platform, also update some platform specific bazel settings
case "$(uname)" in
  Linux)
    PLATFORM="linux" ;;
  Darwin)
    PLATFORM="darwin" ;;
  *NT*)
    PLATFORM="windows"
    IS_NT=true ;;
esac

# Detect the architecture
ARCH="$(uname -m)"
case "$ARCH" in
  aarch64|ppc64le|arm64)
    ARCH="arm64" ;;
  *)
    ARCH="amd64" ;;
esac

# Compute the platform-arch string used to download yq.
case "${PLATFORM}_${ARCH}" in
  linux_arm64|linux_amd64|darwin_arm64|darwin_amd64|windows_amd64)
      ;;  # pass
  *)
    echo "Platform / Architecture is not supported by yq." >&2
    exit 1
    ;;
esac

# Check Python3.8 exist
# TODO(SNOW-845592): ideally we should download py3.8 from conda if not exist. Currently we just fail.
if [ "${ENV}" = "pip" ]; then
    set +eu
    source /opt/rh/rh-python38/enable
    PYTHON38_EXIST=$?
    if [ $PYTHON38_EXIST -ne 0 ]; then
        echo "Failed to execute tests: Python3.8 is not installed."
        rm -rf "${TEMP_TEST_DIR}"
        exit ${PYTHON38_EXIST}
    fi
    set -eu
fi

if [ ${IS_NT} = true ]; then
    EXT=".exe"
    BAZEL_ADDITIONAL_BUILD_FLAGS+=(--nobuild_python_zip)
    BAZEL_ADDITIONAL_BUILD_FLAGS+=(--enable_runfiles)
    BAZEL_ADDITIONAL_STARTUP_FLAGS+=(--output_user_root=D:/broot)
fi

cd "${WORKSPACE}"

# Check and download yq if not presented.
_YQ_BIN="yq${EXT}"
if ! command -v "${_YQ_BIN}" &>/dev/null; then
    TEMP_BIN=$(mktemp -d "${WORKSPACE}/tmp_bin_XXXXX")
    curl -Lsv https://github.com/mikefarah/yq/releases/latest/download/yq_${PLATFORM}_${ARCH}${EXT} -o "${TEMP_BIN}/yq${EXT}" && chmod +x "${TEMP_BIN}/yq${EXT}"
    _YQ_BIN="${TEMP_BIN}/yq${EXT}"
fi

# Create temp release folder
TEMP_TEST_DIR=$(mktemp -d "${WORKSPACE}/tmp_XXXXX")
trap 'rm -rf "${TEMP_TEST_DIR}"' EXIT

pushd ${SNOWML_DIR}
# Get the version from snowflake/ml/version.bzl
VERSION=$(grep -oE "VERSION = \"[0-9]+\\.[0-9]+\\.[0-9]+.*\"" snowflake/ml/version.bzl | cut -d'"' -f2)
echo "Extracted Package Version from code: ${VERSION}"

# Get optional requirements from snowflake/ml/requirements.bzl
OPTIONAL_REQUIREMENTS=()
while IFS='' read -r line; do OPTIONAL_REQUIREMENTS+=("$line"); done < <("${_YQ_BIN}" '.requirements.run_constrained.[] | ... style=""' ci/conda_recipe/meta.yaml)

# Compare test required dependencies with wheel pkg dependencies and exclude tests if necessary
EXCLUDE_TESTS=$(mktemp "${TEMP_TEST_DIR}/exclude_tests_XXXXX")
if [[ ${MODE} = "continuous_run" || ${MODE} = "release" ]]; then
    ./ci/get_excluded_tests.sh -f "${EXCLUDE_TESTS}" -m unused -b "${BAZEL}"
elif [[ ${MODE} = "merge_gate" ]]; then
    ./ci/get_excluded_tests.sh -f "${EXCLUDE_TESTS}" -m all -b "${BAZEL}"
fi

# Generate and copy auto-gen tests.
if [[ ${MODE} = "release" ]]; then
# When release, we build all autogen tests
    "${BAZEL}" "${BAZEL_ADDITIONAL_STARTUP_FLAGS[@]+"${BAZEL_ADDITIONAL_STARTUP_FLAGS[@]}"}" build "${BAZEL_ADDITIONAL_BUILD_FLAGS[@]+"${BAZEL_ADDITIONAL_BUILD_FLAGS[@]}"}" //tests/integ/...
else
# In other cases, we build required utility only.
    "${BAZEL}" "${BAZEL_ADDITIONAL_STARTUP_FLAGS[@]+"${BAZEL_ADDITIONAL_STARTUP_FLAGS[@]}"}" build --build_tag_filters=-autogen_build,-autogen "${BAZEL_ADDITIONAL_BUILD_FLAGS[@]+"${BAZEL_ADDITIONAL_BUILD_FLAGS[@]}"}" //tests/integ/...
fi

# Rsync cannot work well with path that has drive letter in Windows,
# Thus, these two rsync has to use relative path instead of absolute ones.

rsync -av --exclude '*.runfiles_manifest' --exclude '*.runfiles/**' "bazel-bin/tests" .

# Copy tests into temp directory
pushd "${TEMP_TEST_DIR}"
rsync -av --exclude-from "${EXCLUDE_TESTS}" "../${SNOWML_DIR}/tests" .
popd

# Bazel on windows is consuming a lot of memory, let's clean it before proceed to avoid OOM.
if [ ${IS_NT} = true ]; then
    "${BAZEL}" "${BAZEL_ADDITIONAL_STARTUP_FLAGS[@]+"${BAZEL_ADDITIONAL_STARTUP_FLAGS[@]}"}" clean --expunge
    "${BAZEL}" "${BAZEL_ADDITIONAL_STARTUP_FLAGS[@]+"${BAZEL_ADDITIONAL_STARTUP_FLAGS[@]}"}" shutdown
fi

popd

# Build snowml package
if [ "${ENV}" = "pip" ]; then
    # Clean build workspace
    rm -f "${WORKSPACE}"/*.whl

    # Build Snowpark
    if [ "${WITH_SNOWPARK}" = true ]; then
        pushd ${SNOWPARK_DIR}
        rm -rf venv
        python3.8 -m venv venv
        source venv/bin/activate
        python3.8 -m pip install -U pip setuptools wheel
        echo "Building snowpark wheel from main:$(git rev-parse HEAD)."
        pip wheel . --no-deps
        cp "$(find . -maxdepth 1 -iname 'snowflake_snowpark_python-*.whl')" "${WORKSPACE}"
        deactivate
        popd
    fi

    # Build SnowML
    pushd ${SNOWML_DIR}
    "${BAZEL}" "${BAZEL_ADDITIONAL_STARTUP_FLAGS[@]+"${BAZEL_ADDITIONAL_STARTUP_FLAGS[@]}"}" build "${BAZEL_ADDITIONAL_BUILD_FLAGS[@]+"${BAZEL_ADDITIONAL_BUILD_FLAGS[@]}"}" //snowflake/ml:wheel
    cp "$(${BAZEL} info bazel-bin)/snowflake/ml/snowflake_ml_python-${VERSION}-py3-none-any.whl" "${WORKSPACE}"
    popd
else
    # Clean conda cache
    conda clean --all --force-pkgs-dirs -y

    # Clean conda build workspace
    rm -rf "${WORKSPACE}/conda-bld"

    # Build Snowpark
    if [ "${WITH_SNOWPARK}" = true ]; then
        pushd ${SNOWPARK_DIR}
        conda build recipe/ --python=3.8 --numpy=1.16 --croot "${WORKSPACE}/conda-bld"
        popd
    fi

    # Build SnowML
    pushd ${SNOWML_DIR}
    # Build conda package
    conda build --prefix-length 50 --python=3.8 --croot "${WORKSPACE}/conda-bld" ci/conda_recipe
    conda build purge
    popd
fi

# Start testing
pushd "${TEMP_TEST_DIR}"

# Set up common pytest flag
COMMON_PYTEST_FLAG=()
COMMON_PYTEST_FLAG+=(--strict-markers) # Strict the pytest markers to avoid typo in markers
COMMON_PYTEST_FLAG+=(--import-mode=append)
COMMON_PYTEST_FLAG+=(-n logical)

if [ "${ENV}" = "pip" ]; then
    # Copy wheel package
    cp "${WORKSPACE}/snowflake_ml_python-${VERSION}-py3-none-any.whl" "${TEMP_TEST_DIR}"

    # Create testing env
    python3.8 -m venv testenv
    source testenv/bin/activate
    # Install all of the packages in single line,
    # otherwise it will fail in dependency resolution.
    python3.8 -m pip install --upgrade pip
    python3.8 -m pip list
    python3.8 -m pip install "snowflake_ml_python-${VERSION}-py3-none-any.whl[all]" pytest-xdist[psutil] -r "${WORKSPACE}/${SNOWML_DIR}/requirements.txt" --no-cache-dir --force-reinstall
    if [ "${WITH_SNOWPARK}" = true ]; then
        cp "$(find "${WORKSPACE}" -maxdepth 1 -iname 'snowflake_snowpark_python-*.whl')" "${TEMP_TEST_DIR}"
        python3.8 -m pip install "$(find . -maxdepth 1 -iname 'snowflake_snowpark_python-*.whl')" --no-deps --force-reinstall
    fi
    python3.8 -m pip list

    # Run the tests
    set +e
    TEST_SRCDIR="${TEMP_TEST_DIR}" python3.8 -m pytest "${COMMON_PYTEST_FLAG[@]}" -m "not pip_incompatible" tests/integ/
    TEST_RETCODE=$?
    set -e
else
    # Create local conda channel
    conda index "${WORKSPACE}/conda-bld"

    # Clean conda cache
    conda clean --all --force-pkgs-dirs -y

    # Create testing env
    conda create -y -p testenv -c "${WORKSPACE}/conda-bld" -c "https://repo.anaconda.com/pkgs/snowflake/" --override-channels "python=3.8" snowflake-ml-python pytest-xdist psutil inflection "${OPTIONAL_REQUIREMENTS[@]}"
    conda list -p testenv

    # Run integration tests
    set +e
    TEST_SRCDIR="${TEMP_TEST_DIR}" conda run -p testenv --no-capture-output python -m pytest "${COMMON_PYTEST_FLAG[@]}" tests/integ/
    TEST_RETCODE=$?
    set -e

    # Clean the conda environment
    conda env remove -p testenv
fi

popd

echo "Done running ${PROG}"
# Pytest exit code
#   0: Success;
#   5: no tests found
# See https://docs.pytest.org/en/7.1.x/reference/exit-codes.html
if [[ ${MODE} = "merge_gate" && ${TEST_RETCODE} -eq 5 ]]; then
    exit 0
fi
exit ${TEST_RETCODE}
