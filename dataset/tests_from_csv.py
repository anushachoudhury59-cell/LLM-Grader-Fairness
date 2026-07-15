"""
promptfoo test generator for BUILD-dataset-spec.md. Reads whichever run_<N>.csv
is set via the RUN_CSV env var (defaults to run_1.csv) and yields one test per
row, with answer_text/customer_message as vars (both required so the grader
sees the reply plus the complaint it's responding to -- and so the name reaches
the grader at all) and the rest as metadata for post-hoc analysis.
"""
import csv
import os

RUN_CSV = os.environ.get("RUN_CSV", "run_1.csv")

def generate_tests():
    with open(RUN_CSV) as f:
        rows = list(csv.DictReader(f))

    tests = []
    for row in rows:
        tests.append(
            {
                "vars": {
                    "answer_text": row["answer_text"],
                    "customer_message": row["customer_message"],
                },
                "metadata": {
                    "unit_id": row["unit_id"],
                    "source_category": row["source_category"],
                    "quality": row["quality"],
                    "name_group": row["name_group"],
                    "name": row["name"],
                },
            }
        )
    return tests
