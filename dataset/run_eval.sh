#!/bin/bash
# Runs the pointwise-judge-bias eval (plan-pointwise-judge-bias.md) for both
# graders: 3 repeats each, cache cleared between every repeat, on run_1.csv.
# Cache-clearing is mandatory -- a cached repeat gives a fake noise floor of
# exactly zero and the whole bias-vs-noise comparison becomes meaningless.
set -euo pipefail
cd "$(dirname "$0")"

# Load OPENAI_API_KEY / ANTHROPIC_API_KEY, preferring ../.env, falling back to
# ../api_keys/api_key.json (both gitignored)
if [ -f "../.env" ]; then
  set -a
  source "../.env"
  set +a
elif [ -f "../api_keys/api_key.json" ]; then
  export OPENAI_API_KEY=$(python3 -c "import json; print(json.load(open('../api_keys/api_key.json'))['OPENAI_API_KEY'])")
  export ANTHROPIC_API_KEY=$(python3 -c "import json; print(json.load(open('../api_keys/api_key.json'))['ANTHROPIC_API_KEY'])")
fi

RUN_CSV_PATH="${1:-run_1.csv}"
mkdir -p results

for provider in openai anthropic; do
  config="promptfooconfig.yaml"
  if [ "$provider" = "anthropic" ]; then
    config="promptfooconfig.anthropic.yaml"
  fi

  for repeat in 1 2 3; do
    out="results/${provider}_repeat${repeat}.json"
    if [ -f "$out" ]; then
      echo "=== $provider repeat $repeat already done, skipping ==="
      continue
    fi
    echo "=== $provider repeat $repeat (config: $config, data: $RUN_CSV_PATH) ==="
    npx promptfoo@latest cache clear
    # promptfoo exits non-zero whenever any row's assertion fails its pass
    # threshold -- expected here (bad-quality rows should score low), not a
    # real error, so don't let `set -e` treat it as fatal.
    RUN_CSV="$RUN_CSV_PATH" npx promptfoo@latest eval -c "$config" -o "$out" || true
    if [ ! -f "$out" ]; then
      echo "ERROR: $out was not written -- a real failure occurred, stopping."
      exit 1
    fi
  done
done

echo "Done. Results in dataset/results/"
