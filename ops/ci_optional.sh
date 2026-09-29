#!/bin/sh
# Runs `make <target>` for each target that the Makefile defines, and says so for the ones it does not. The CI calls this for the
# checks that other branches add (data/ML validation, ...), so merging one of them turns its check on without editing the
# workflow, and a branch that does not have the target yet is not a failure.
#   sh ops/ci_optional.sh validate-data-ml
for target in "$@"; do
  if make -n "$target" >/dev/null 2>&1; then
    echo "::group::make $target"
    make "$target" || exit 1
    echo "::endgroup::"
  else
    echo "skipped: this checkout has no 'make $target'"
  fi
done
