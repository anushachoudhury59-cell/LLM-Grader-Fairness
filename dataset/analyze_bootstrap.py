"""
Bootstrap analysis: does any single name score consistently worse, hidden
inside the White/Black aggregate?

Why the earlier per-name breakdown (in the conversation, not saved as code)
was wrong: raw per-name means are confounded by *which units that name
happened to land on*. Names are drawn independently per unit per run, so in
any single run some names get assigned to more "good"-quality or easier
tickets than others by chance. A name's raw average score partly reflects
that luck, not the grader's treatment of the name.

Fix: a fixed-effects (demeaned) estimate. For every unit (one of the 40
ticket x quality combinations), compute unit_mean = the average score that
unit received across *every* appearance in *every* bootstrap run, regardless
of which name was attached. That's the unit's own baseline difficulty/quality,
estimated from many draws. Then for each name, average
  (observed score - unit_mean of the unit it was attached to)
across every run where that name appeared. This isolates "does the grader
score this name's tickets higher or lower than that ticket's own baseline
would predict" -- exactly the question asked, and it needs multiple runs
(the bootstrap) per name to have enough (unit, run) pairs to average over.
"""
import json
import statistics
from collections import defaultdict
from pathlib import Path

PROVIDERS = ["openai", "anthropic"]
BOOTSTRAP_DIR = Path(__file__).parent / "results" / "bootstrap"
WHITE = {"Emily", "Greg", "Brendan", "Anne", "Matthew"}
BLACK = {"Lakisha", "Jamal", "Darnell", "Ebony", "Tyrone"}


def load_all_runs(provider: str) -> list[dict]:
    rows = []
    dropped = 0
    for path in sorted(BOOTSTRAP_DIR.glob(f"{provider}_run*.json")):
        with open(path) as f:
            data = json.load(f)
        for r in data["results"]["results"]:
            meta = r["testCase"]["metadata"]
            grading = r.get("gradingResult", {}) or {}
            components = grading.get("componentResults") or []
            # Same grader-infra-error filter as analyze_results.py -- a quota/5xx
            # failure returns score=0 with graderError=True in the metadata,
            # indistinguishable from a real bad score unless checked explicitly.
            # Confirmed present in this data: OpenAI hit HTTP 429 partway through
            # several bootstrap runs. Drop rather than impute.
            if components and components[0].get("metadata", {}).get("graderError"):
                dropped += 1
                continue
            rows.append(
                {
                    "unit_id": meta["unit_id"],
                    "quality": meta["quality"],
                    "name_group": meta["name_group"],
                    "name": meta["name"],
                    "score": r["score"],
                }
            )
    if dropped:
        print(f"  {provider}: dropped {dropped} grader-error rows across all runs")
    return rows


def per_name_effects(rows: list[dict]) -> dict:
    # unit baseline = mean score of that unit across every draw in every run
    by_unit = defaultdict(list)
    for r in rows:
        by_unit[r["unit_id"]].append(r["score"])
    unit_mean = {u: statistics.mean(v) for u, v in by_unit.items()}

    residuals_by_name = defaultdict(list)
    for r in rows:
        residuals_by_name[r["name"]].append(r["score"] - unit_mean[r["unit_id"]])

    effects = {}
    for name, residuals in residuals_by_name.items():
        n = len(residuals)
        mean_effect = statistics.mean(residuals)
        stdev = statistics.stdev(residuals) if n > 1 else 0.0
        se = stdev / (n ** 0.5) if n > 1 else 0.0
        effects[name] = {
            "n": n,
            "mean_effect": mean_effect,
            "se": se,
            # rough 95% CI; not claiming normality, just a magnitude check
            "ci_low": mean_effect - 1.96 * se,
            "ci_high": mean_effect + 1.96 * se,
            "group": "white" if name in WHITE else "black",
        }
    return effects


def analyze_provider(provider: str) -> dict:
    rows = load_all_runs(provider)
    n_runs = len(sorted(BOOTSTRAP_DIR.glob(f"{provider}_run*.json")))
    effects = per_name_effects(rows)

    white_scores = [r["score"] for r in rows if r["name_group"] == "white"]
    black_scores = [r["score"] for r in rows if r["name_group"] == "black"]
    overall_delta = statistics.mean(white_scores) - statistics.mean(black_scores)

    return {
        "provider": provider,
        "n_runs": n_runs,
        "n_rows": len(rows),
        "overall_name_swap_delta": overall_delta,
        "per_name_effects": effects,
    }


def main():
    summary = {"providers": [analyze_provider(p) for p in PROVIDERS]}
    out_path = BOOTSTRAP_DIR / "per_name_summary.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Wrote {out_path}\n")

    for p in summary["providers"]:
        print(f"{p['provider']} ({p['n_runs']} runs, {p['n_rows']} rows)")
        print(f"  overall name-swap delta: {p['overall_name_swap_delta']:+.4f}")
        rows = sorted(p["per_name_effects"].items(), key=lambda kv: kv[1]["mean_effect"])
        for name, e in rows:
            flag = "" if e["ci_low"] <= 0 <= e["ci_high"] else "  <- CI excludes 0"
            print(f"    {e['group']:<6} {name:<10} n={e['n']:>3}  effect={e['mean_effect']:+.4f}  95% CI [{e['ci_low']:+.4f}, {e['ci_high']:+.4f}]{flag}")
        print()


if __name__ == "__main__":
    main()
