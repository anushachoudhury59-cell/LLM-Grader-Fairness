"""
Deliverable #2 from BUILD-dataset-spec.md: given a run number, fill each of
the 40 base units with one randomly-drawn White-coded and one Black-coded
name, producing 80 rows for that run. The run number seeds the RNG so a given
run is always reproducible, while different run numbers draw different names
(so pairings shift across runs -- Emily vs. Tyrone one run, Emily vs. Jamal
the next).
"""
import csv
import random
import sys

WHITE = ["Emily", "Greg", "Brendan", "Anne", "Matthew"]
BLACK = ["Lakisha", "Jamal", "Darnell", "Ebony", "Tyrone"]


def make_run(run_n: int) -> list[dict]:
    random.seed(run_n)
    with open("base_units.csv") as f:
        units = list(csv.DictReader(f))

    rows = []
    for u in units:
        white_name = random.choice(WHITE)
        black_name = random.choice(BLACK)
        for name, group in [(white_name, "white"), (black_name, "black")]:
            rows.append(
                {
                    "unit_id": u["unit_id"],
                    "source_category": u["source_category"],
                    "ticket_id": u["ticket_id"],
                    "quality": u["quality"],
                    "customer_message": u["customer_message"].replace("{{NAME}}", name),
                    "answer_text": u["answer_text"],
                    "name": name,
                    "name_group": group,
                }
            )
    return rows


def main():
    if len(sys.argv) != 2:
        print("usage: python make_run.py <run_number>")
        sys.exit(1)
    run_n = int(sys.argv[1])

    rows = make_run(run_n)
    assert len(rows) == 80, f"expected 80 rows, got {len(rows)}"

    fieldnames = ["unit_id", "source_category", "ticket_id", "quality", "customer_message", "answer_text", "name", "name_group"]
    out_path = f"run_{run_n}.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
