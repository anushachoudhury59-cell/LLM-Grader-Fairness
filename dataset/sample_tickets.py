"""
Step 1 of BUILD-dataset-spec.md: pull real support tickets from Kaggle and
sample 20 of them spread across category, type, priority, and scenario theme.

Source: tobiasbueck/multilingual-customer-support-tickets
  (file: dataset-tickets-multi-lang-4-20k.csv, English rows only)

The originally-specified dataset (muqaddasejaz/customer-support-ticket-dataset)
turned out to be unusable: every row has an unfilled "{product_purchased}"
template placeholder and the surrounding text is synthetic filler that doesn't
read as real customer writing (confirmed by inspection, not assumed).

This dataset's `queue` field maps onto the spec's "category" dimension (10
distinct queues). `type` (Incident/Request/Problem/Change) and `priority`
(low/medium/high) are real dataset fields used as balance dimensions instead
of a hand-rolled tone heuristic. `body` is the actual ticket text -- diversity
check confirmed 0 exact duplicates and varied complaint substance, though many
rows share stock "Hello Customer Support, I am contacting you..." boilerplate,
so near-duplicate openers are screened out below.

The underlying generator also reuses a small pool of scenario premises
(medical/HIPAA data, investment/finance, marketing campaigns, project-mgmt
software, data-analytics tooling) across queues -- confirmed via keyword
crosstab that every queue has multiple themes represented, so themes are
balanced as a 4th soft dimension rather than narrowed to one.

Output: sampled_tickets.csv (20 rows) with columns:
  ticket_id, source_category, subject, raw_customer_text, char_len, type, priority, theme
"""
import csv
import re

import kagglehub
import pandas as pd

SEED = 42  # base content is built once, not per-run -- fixed for reproducibility
N_PER_QUEUE = 2
MIN_LEN, MAX_LEN = 80, 700  # drop near-empty rows and overly long ones
KEEP_COLUMNS = ["subject", "body", "type", "queue", "priority", "language"]

# Catches leftover template artifacts the source generator didn't fill in
# (<tel_num>, <acc_num>, <name>, [Date], [Invoice Number], etc.) -- confirmed via
# corpus scan that ~9.4% of rows carry one of these; affected rows are dropped
# rather than hand-patched since the placeholder vocabulary is long-tailed and
# some (<name>, [Name], [Customer Name]) would collide with our own {{NAME}}.
PLACEHOLDER_PATTERN = re.compile(r"<[a-zA-Z_]+>|\{[a-zA-Z_]+\}|\[[A-Za-z ]+\]")

THEME_KEYWORDS = {
    "medical/healthcare": ["medical", "hipaa", "hospital", "patient", "healthcare"],
    "investment/finance": ["investment", "portfolio", "financial institution", "trading"],
    "marketing campaign": ["marketing campaign", "social media", "brand", "ad placements", "engagement"],
    "project mgmt software": ["project management software", "gitlab", "jira", "scrivener"],
    "data analytics tool": ["data analytics", "analytics tool", "analytics platform"],
}


def load_english_tickets() -> pd.DataFrame:
    path = kagglehub.dataset_download("tobiasbueck/multilingual-customer-support-tickets")
    csv_path = f"{path}/dataset-tickets-multi-lang-4-20k.csv"
    df = pd.read_csv(csv_path, usecols=KEEP_COLUMNS)
    df = df[df["language"] == "en"].copy()
    df = df.dropna(subset=["body", "queue", "type", "priority"])
    df["subject"] = df["subject"].fillna("")
    return df


def clean_text(text: str) -> str:
    text = text.replace("\\n", " ").replace("<br>", " ")  # literal escapes / stray HTML in source rows
    text = re.sub(r"\[Your Name\]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    return text


def theme_of(text: str) -> str:
    lowered = text.lower()
    for name, keywords in THEME_KEYWORDS.items():
        if any(kw in lowered for kw in keywords):
            return name
    return "other"


def sample_tickets(df: pd.DataFrame) -> tuple[list[dict], dict, dict, dict]:
    df = df.copy()
    df["clean_body"] = df["body"].astype(str).apply(clean_text)
    df["char_len"] = df["clean_body"].str.len()
    df["opener"] = df["clean_body"].str[:30].str.lower()
    df["theme"] = df["clean_body"].apply(theme_of)
    df = df[(df["char_len"] >= MIN_LEN) & (df["char_len"] <= MAX_LEN)]
    df = df[df["clean_body"].str.endswith((".", "?", "!", '"', "'"))]  # drop rows truncated mid-sentence in the source CSV
    df = df[~df["clean_body"].str.contains(PLACEHOLDER_PATTERN)]  # drop rows with unfilled template artifacts
    df = df.drop_duplicates(subset="clean_body")

    type_count = {t: 0 for t in sorted(df["type"].unique())}
    priority_count = {p: 0 for p in sorted(df["priority"].unique())}
    theme_count = {th: 0 for th in sorted(df["theme"].unique())}
    used_openers = set()

    queues = sorted(df["queue"].unique())
    rows = []
    ticket_id = 1
    for queue in queues:
        pool = df[df["queue"] == queue].sample(frac=1, random_state=SEED)  # shuffle deterministically
        picks = _greedy_pick_for_queue(pool, N_PER_QUEUE, type_count, priority_count, theme_count, used_openers)
        for pick in picks:
            type_count[pick["type"]] += 1
            priority_count[pick["priority"]] += 1
            theme_count[pick["theme"]] += 1
            used_openers.add(pick["opener"])
            rows.append(
                {
                    "ticket_id": ticket_id,
                    "source_category": queue,
                    "subject": pick.get("subject", ""),
                    "raw_customer_text": pick["clean_body"],
                    "char_len": pick["char_len"],
                    "type": pick["type"],
                    "priority": pick["priority"],
                    "theme": pick["theme"],
                }
            )
            ticket_id += 1

    return rows, type_count, priority_count, theme_count


def _greedy_pick_for_queue(pool, n, type_count, priority_count, theme_count, used_openers):
    remaining = pool[~pool["opener"].isin(used_openers)].to_dict("records")
    picks = []
    for _ in range(n):
        if not remaining:
            break
        remaining.sort(
            key=lambda r: (
                type_count[r["type"]] + priority_count[r["priority"]] + theme_count[r["theme"]],
                r["opener"] in {p["opener"] for p in picks},  # tie-break: avoid dup openers within pick
            )
        )
        best = remaining.pop(0)
        picks.append(best)
        remaining = [r for r in remaining if r["opener"] != best["opener"]]
        type_count = {**type_count, best["type"]: type_count[best["type"]] + 1}
        priority_count = {**priority_count, best["priority"]: priority_count[best["priority"]] + 1}
        theme_count = {**theme_count, best["theme"]: theme_count[best["theme"]] + 1}
    return picks


def main():
    df = load_english_tickets()
    rows, type_count, priority_count, theme_count = sample_tickets(df)
    assert len(rows) == 20, f"expected 20 tickets, got {len(rows)}"

    fieldnames = ["ticket_id", "source_category", "subject", "raw_customer_text", "char_len", "type", "priority", "theme"]
    with open("sampled_tickets.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} tickets to sampled_tickets.csv")
    print(f"Categories: {sorted(set(r['source_category'] for r in rows))}")
    print(f"Type balance: {type_count}")
    print(f"Priority balance: {priority_count}")
    print(f"Theme balance: {theme_count}")
    lens = [r["char_len"] for r in rows]
    print(f"Length range: {min(lens)}-{max(lens)} chars")


if __name__ == "__main__":
    main()
