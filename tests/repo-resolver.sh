#!/bin/sh

# This is used by argocd-renderer to resolve repositories before processing them.
# The script expects 3 args: the repo URL to resolve, repo revision, and a temp dir.

cd "$(dirname "$(realpath "$0")")"

if [ "$#" -ne 3 ]; then
    echo "Usage: $0 <repo-url> <revision> <temp-dir>" >&2
    exit 1
fi

msg_stderr () {
    echo "    ... [repo-resolver.sh] $@" >&2
}

REPO_URL="$1"
REVISION="$2"
TEMP_DIR="$3"

if [ "$REPO_URL" = "some-url" -a "$REVISION" = "rev2" ]; then
    RESULT="./tests/helm-repo-01"
fi

if [ "$REPO_URL" = "some-url-k" -a "$REVISION" = "rev3" ]; then
    RESULT="./tests/kustomize-repo-01"
fi

if [ "$REPO_URL" = "https://example.com" -a "$REVISION" = "HEAD" ]; then
    RESULT="./tests/simple-repo-01"
fi

if [ -n "$RESULT" ]; then
    msg_stderr "Resolved '$REPO_URL' @ '$REVISION' as '$RESULT'."
    echo "$RESULT"
    exit 0
fi

msg_stderr "Unknown repo-url or revision: $REPO_URL $REVISION"
exit 1
