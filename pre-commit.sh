#!/bin/sh
# This is supposed to be run by git pre-commit hook and installed via prepare.sh.

set -e

cd "$(dirname "$(realpath "$0")")"

./test.sh || exit 11
