#!/bin/sh

set -e

cd "$(dirname "$(realpath "$0")")"

# Install ./pre-commit.sh as pre-commit hook for git.
echo "Installing pre-commit hook..."
ln -sf ../../pre-commit.sh .git/hooks/pre-commit
