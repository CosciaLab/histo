#!/usr/bin/env bash
# Lint nextflow_schema.json against itself and nextflow.config.
#
# Two callers:
#   prek passes changed file names as arguments; lint runs unconditionally.
#   Claude Code (PostToolUse) passes a JSON payload on stdin; lint runs only when the edited
#   file is nextflow_schema.json or nextflow.config. Exit 2 feeds the error back to the agent.
#
# schema_params is included because `schema lint` alone misses params set only in the config.

set -uo pipefail

root="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"

if [ $# -eq 0 ]; then
    edited=$(python3 -c 'import json, sys; print(json.load(sys.stdin).get("tool_input", {}).get("file_path", ""))')
    case "$edited" in
        */nextflow_schema.json | */nextflow.config) ;;
        *) exit 0 ;;
    esac
fi

if ! out=$(nf-core pipelines lint --dir "$root" -k schema_lint -k schema_params 2>&1); then
    # Keep parse errors and the failed-tests box; drop the module tables nf-core appends.
    echo "$out" | awk '/^CRITICAL/ {crit=1} crit && !/^(CRITICAL| )/ {crit=0} crit {print}
        /\[✗\].*Failed/ {box=1} box {print} box && /╰/ {box=0}' >&2
    echo "nextflow_schema.json failed lint: nf-core pipelines lint --dir . -k schema_lint -k schema_params" >&2
    exit 2
fi
