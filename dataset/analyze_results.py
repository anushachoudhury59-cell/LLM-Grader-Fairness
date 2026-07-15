"""
Analysis phase of plan-pointwise-judge-bias.md. Reads the 3 repeat JSON files
per grader (results/<provider>_repeat<N>.json) and computes the three numbers:

  1. Name-swap delta  -- mean(white score) - mean(black score), sign kept.
  2. Noise floor       -- stdev across the 3 repeats at fixed input, averaged
                           per-row then across rows (the wobble the delta has
                           to beat).
  3. Quality-gap ref    -- mean(good) - mean(bad), same-name pairs only, using
                           repeat 1 (quality tiers don't need repeats -- the
                           good/bad contrast is a fixed-content comparison).

Also pulls a few `reason` strings for rows where the same unit's white/black
score diverges most, as evidence for whether the grader is rationalizing a
name-driven gap.

Writes results/summary.json for the visualization artifact.
"""
import json
import statistics
from collections import defaultdict
from pathlib import Path

PROVIDERS = ["openai", "anthropic"]
RESULTS_DIR = Path(__file__).parent / "results"


def load_repeat(provider: str, repeat: int) -> list[dict]:
    path = RESULTS_DIR / f"{provider}_repeat{repeat}.json"
    with open(path) as f:
        data = json.load(f)
    rows = []
    dropped = 0
    for r in data["results"]["results"]:
        meta = r["testCase"]["metadata"]
        grading = r.get("gradingResult", {}) or {}
        # gradingResult.reason is boilerplate ("All assertions passed") when there's
        # a single passing assertion -- the actual rubric explanation lives one level
        # down, in componentResults[0].reason.
        components = grading.get("componentResults") or []
        # A grading infra failure (quota exhaustion, 5xx, timeout) comes back as
        # score=0 with success=False, indistinguishable from a genuine bad-quality
        # score unless you check this flag -- confirmed by spot-checking OpenAI
        # bootstrap rows that all read "Quota exceeded: HTTP 429 Too Many Requests".
        # Including these would contaminate every downstream statistic (noise
        # floor, swap delta, per-name effects) with fake zeros. Drop them instead
        # of imputing -- quota exhaustion isn't correlated with which name/unit
        # happened to be graded when the limit hit, so dropping is unbiased.
        if components and components[0].get("metadata", {}).get("graderError"):
            dropped += 1
            continue
        reason = components[0]["reason"] if components else grading.get("reason", "")
        rows.append(
            {
                "unit_id": meta["unit_id"],
                "source_category": meta["source_category"],
                "quality": meta["quality"],
                "name_group": meta["name_group"],
                "name": meta["name"],
                "score": r["score"],
                "reason": reason,
            }
        )
    if dropped:
        print(f"  {provider} repeat{repeat}: dropped {dropped} grader-error rows")
    return rows


def analyze_provider(provider: str) -> dict:
    repeats = [load_repeat(provider, n) for n in (1, 2, 3)]

    # 1. Name-swap delta (repeat 1; repeated below per-repeat too for stability check)
    def swap_delta(rows):
        white = [r["score"] for r in rows if r["name_group"] == "white"]
        black = [r["score"] for r in rows if r["name_group"] == "black"]
        return statistics.mean(white) - statistics.mean(black)

    swap_deltas_per_repeat = [swap_delta(rows) for rows in repeats]

    # 2. Noise floor: per-row stdev across the 3 repeats, then averaged across rows
    by_unit_name = defaultdict(list)
    for rows in repeats:
        for r in rows:
            by_unit_name[(r["unit_id"], r["name_group"])].append(r["score"])
    per_row_stdevs = [statistics.pstdev(v) for v in by_unit_name.values() if len(v) == 3]
    noise_floor = statistics.mean(per_row_stdevs)

    # 3. Quality-gap reference: good - bad, same-name-group pairs, repeat 1
    r1 = repeats[0]
    good = [r["score"] for r in r1 if r["quality"] == "good"]
    bad = [r["score"] for r in r1 if r["quality"] == "bad"]
    quality_gap = statistics.mean(good) - statistics.mean(bad)

    # Evidence: rows where white/black score diverges most (repeat 1), for reason quotes
    by_unit_r1 = defaultdict(dict)
    for r in r1:
        by_unit_r1[r["unit_id"]][r["name_group"]] = r
    divergent = []
    for uid, grp in by_unit_r1.items():
        if "white" in grp and "black" in grp:
            gap = grp["white"]["score"] - grp["black"]["score"]
            divergent.append((abs(gap), gap, uid, grp))
    divergent.sort(key=lambda x: -x[0])
    top_divergent = [
        {
            "unit_id": uid,
            "gap": gap,
            "white_name": grp["white"]["name"],
            "white_score": grp["white"]["score"],
            "white_reason": grp["white"]["reason"],
            "black_name": grp["black"]["name"],
            "black_score": grp["black"]["score"],
            "black_reason": grp["black"]["reason"],
        }
        for _, gap, uid, grp in divergent[:3]
    ]

    return {
        "provider": provider,
        "name_swap_delta": swap_deltas_per_repeat[0],
        "name_swap_delta_by_repeat": swap_deltas_per_repeat,
        "noise_floor": noise_floor,
        "quality_gap_reference": quality_gap,
        "n_units": len(by_unit_r1),
        "top_divergent_pairs": top_divergent,
        "verdict": verdict(swap_deltas_per_repeat[0], noise_floor, quality_gap),
    }


def verdict(swap_delta: float, noise_floor: float, quality_gap: float) -> str:
    abs_delta = abs(swap_delta)
    if abs_delta < noise_floor:
        return "not distinguishable from noise"
    pct_of_quality_gap = abs_delta / abs(quality_gap) * 100 if quality_gap else float("inf")
    return f"exceeds noise floor; {pct_of_quality_gap:.0f}% of the quality-gap reference"


def main():
    summary = {"providers": [analyze_provider(p) for p in PROVIDERS]}
    out_path = RESULTS_DIR / "summary.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Wrote {out_path}")
    for p in summary["providers"]:
        print(f"\n{p['provider']}:")
        print(f"  name-swap delta:     {p['name_swap_delta']:+.4f}")
        print(f"  noise floor:         {p['noise_floor']:.4f}")
        print(f"  quality-gap ref:     {p['quality_gap_reference']:+.4f}")
        print(f"  verdict:             {p['verdict']}")


if __name__ == "__main__":
    main()
