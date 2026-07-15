#!/bin/bash
# Bootstrap phase (BUILD-dataset-spec.md "what happens next"): grade run_1..run_N,
# one pass per provider per run. Only 1 repeat per run -- the noise floor (score
# wobble at *fixed* input) was already measured by run_eval.sh's 3-repeat study
# on run_1. What varies here is *which names got drawn* for each unit, run to
# run -- that's the axis the per-name analysis needs statistical power on.
set -euo pipefail
cd "$(dirname "$0")"

if [ -f "../.env" ]; then
  set -a; source "../.env"; set +a
elif [ -f "../api_keys/api_key.json" ]; then
  export OPENAI_API_KEY=$(python3 -c "import json; print(json.load(open('../api_keys/api_key.json'))['OPENAI_API_KEY'])")
  export ANTHROPIC_API_KEY=$(python3 -c "import json; print(json.load(open('../api_keys/api_key.json'))['ANTHROPIC_API_KEY'])")
fi

N_RUNS="${1:-10}"
mkdir -p results/bootstrap

for run_n in $(seq 1 "$N_RUNS"); do
  csv="run_${run_n}.csv"
  if [ ! -f "$csv" ]; then
    python3 make_run.py "$run_n"
  fi

  for provider in openai anthropic; do
    config="promptfooconfig.yaml"
    if [ "$provider" = "anthropic" ]; then
      config="promptfooconfig.anthropic.yaml"
    fi

    out="results/bootstrap/${provider}_run${run_n}.json"
    if [ -f "$out" ]; then
      echo "=== $provider run $run_n already done, skipping ==="
      continue
    fi

    echo "=== $provider run $run_n (config: $config, data: $csv) ==="
    npx promptfoo@latest cache clear
    RUN_CSV="$csv" npx promptfoo@latest eval -c "$config" -o "$out" || true
    if [ ! -f "$out" ]; then
      echo "ERROR: $out was not written -- a real failure occurred, stopping."
      exit 1
    fi
  done
done

echo "Done. Bootstrap results in dataset/results/bootstrap/"
