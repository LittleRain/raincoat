#!/usr/bin/env bash
# One command for goal criterion (4): bank validation, rule evidence gates,
# release manifest check, unit tests, and a report regenerated from the newest
# evaluation artifacts on disk. It never spends new model calls.
set -euo pipefail

cd "$(dirname "$0")/.."

# test.sh already runs the case/rule/release gates plus Python and Swift tests.
bash scripts/test.sh

newest_run() {
    # Directories that actually hold a runs.jsonl, newest first.
    find .build/evaluation -name runs.jsonl -maxdepth 2 -print 2>/dev/null \
        | xargs -n1 dirname 2>/dev/null | xargs -n1 stat -f '%m %N' 2>/dev/null \
        | sort -rn | head -1 | cut -d' ' -f2-
}

run_dir="$(newest_run || true)"
if [ -n "${run_dir}" ]; then
    echo "run report: ${run_dir}"
    python3 scripts/eval/run.py --out "${run_dir}" --targets bitto,workbuddy --versions A,C --report-only
    if [ -d "${run_dir%/}" ] && [ -f "${run_dir}/private-mapping.json" ]; then
        # Judge output lives in a sibling directory; pick the newest one that
        # actually has judgments, or honour an explicit JUDGE_DIR.
        judge_dir="${JUDGE_DIR:-}"
        if [ -z "${judge_dir}" ]; then
            judge_dir="$(find .build/evaluation -name judges.jsonl -maxdepth 2 -print 2>/dev/null \
                | xargs -n1 dirname 2>/dev/null | xargs -n1 stat -f '%m %N' 2>/dev/null \
                | sort -rn | head -1 | cut -d' ' -f2-)"
        fi
        if [ -n "${judge_dir}" ] && [ -d "${judge_dir}" ]; then
            echo "judge report: ${judge_dir}"
            if ! python3 scripts/eval/run_judge.py --source "${run_dir}" --base A --new C \
                --judges bitto,workbuddy --out "${judge_dir}" --report-only 2>/dev/null; then
                echo "judge report skipped (judging in progress or no completed batches)"
            fi
        fi
    fi
else
    echo "no evaluation artifacts yet; skipped report generation"
fi

echo "regression: done"
