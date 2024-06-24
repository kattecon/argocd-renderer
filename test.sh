#!/bin/sh

cd "$(dirname "$(realpath "$0")")"

yamllint -s -f standard . || exit 99

sep() {
    echo ""
    echo "-------------------------------------------------------------------------"
    echo "$@"
    echo ""
}

test() {
    name="$1"
    shift

    sep

    ./argocd-renderer.py \
        "$@" \
        -r ./tests/repo-resolver.sh \
        -o tests/$name/result.tmp.yaml \
         tests/$name/input.yaml \
            || exit "$?"

    if diff -u tests/$name/expect.yaml tests/$name/result.tmp.yaml; then
        echo ""
        echo "Check '$name' passed."
    else
        echo ""
        echo "Check '$name' failed."
        echo ""
        echo "If the result is correct, then the expectation for test can be updated like this:"
        echo "  cp \"tests/$name/result.tmp.yaml\" \"tests/${name}/expect.yaml\""
        exit 1
    fi
}

# ---- Helm
test "test-01"
test "test-02"
test "test-03"
test "test-04"
test "test-05" --helm-args="['--set', 'v1=via-arg-arg']"
test "test-06"

# ---- Kustomize
test "test-20"

# ---- As-is
test "test-40"
