#!/usr/bin/env bash
# Copy the read-only /repo into /work, then run the given command there.
set -euo pipefail
rsync -a --delete \
    --exclude .git --exclude work --exclude .nextflow\* --exclude .nf-test --exclude local_test_datasets \
    --exclude fixture --exclude .venv --exclude scratch /repo/ /work/
cd /work
exec "$@"
