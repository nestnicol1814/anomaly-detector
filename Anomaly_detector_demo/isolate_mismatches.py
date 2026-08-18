"""
isolate_mismatches.py -- pull the disagreeing cases out of the per-case
results so they can be hunted down one by one.

Run AFTER test.py has written per_case_results.csv.

    python isolate_mismatches.py                          # uses default paths below
    python isolate_mismatches.py path/to/per_case_results.csv path/to/output_dir

Writes four CSVs into the output dir:

  hallucinated_cases.csv   one row per CASE where the AI claimed >=1 rule ML did not
  missed_cases.csv         one row per CASE where ML flagged >=1 rule the AI did not
  hallucinated_rules.csv   one row per (case, rule) pair -- the hallucinated list EXPLODED
  missed_rules.csv         one row per (case, rule) pair -- the missed list EXPLODED

The *_cases files keep every column from the results (precision, recall,
f1, counts) so you have full context per case. The *_rules files are the
flat "hit list": each line is exactly one rule on one transaction, with the
company code and doc number split back out so you can look the transaction
up in the source systems directly.

A case can appear in BOTH hallucinated and missed (AI got one rule wrong in
each direction) -- that's expected, not a bug.
"""
import os
import sys

import pandas as pd

DEFAULT_RESULTS = r"C:\Users\NGarbea\OneDrive - NESTLE\Documents\Anomaly_detector_demo\per_case_results.csv"
DEFAULT_OUT_DIR = r"C:\Users\NGarbea\OneDrive - NESTLE\Documents\Anomaly_detector_demo"


def split_id(df):
    """transaction_id is '<company_code>_<doc_nr>'. Split it back out so the
    output can be joined against the source Excel files / looked up in SAP."""
    parts = df["transaction_id"].str.split("_", n=1, expand=True)
    df = df.copy()
    df.insert(1, "company_code", parts[0])
    df.insert(2, "document_nr", parts[1])
    return df


def explode_rules(cases, list_col, rule_col_name):
    """Turn 'R03,R07' in one cell into one row per rule."""
    if cases.empty:
        return pd.DataFrame(columns=["transaction_id", "company_code", "document_nr", rule_col_name])
    out = cases[["transaction_id", "company_code", "document_nr", list_col]].copy()
    out[rule_col_name] = out[list_col].str.split(",")
    out = out.explode(rule_col_name)
    out[rule_col_name] = out[rule_col_name].str.strip()
    out = out[out[rule_col_name].notna() & (out[rule_col_name] != "") & (out[rule_col_name] != "-")]
    return out.drop(columns=[list_col]).reset_index(drop=True)


def main():
    results_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_RESULTS
    out_dir = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_OUT_DIR

    if not os.path.isfile(results_path):
        sys.exit(f"results file not found: {results_path}\n"
                 f"run test.py first, or pass the path as the first argument")
    os.makedirs(out_dir, exist_ok=True)

    df = pd.read_csv(results_path, dtype={"transaction_id": str,
                                          "hallucinated_rules": str,
                                          "missed_rules": str})
    for col in ("n_hallucinated", "n_missed"):
        if col not in df.columns:
            sys.exit(f"{results_path} has no column {col!r} -- is this the per_case_results.csv from test.py?")

    df = split_id(df)

    # --- the two disagreement populations ---
    hallucinated_cases = df[df["n_hallucinated"] > 0].copy()   # AI said triggered, ML said no
    missed_cases = df[df["n_missed"] > 0].copy()               # ML said triggered, AI said no
    both = hallucinated_cases.merge(missed_cases[["transaction_id"]], on="transaction_id")

    # sort so the worst offenders are at the top of each file
    hallucinated_cases = hallucinated_cases.sort_values(["n_hallucinated", "transaction_id"], ascending=[False, True])
    missed_cases = missed_cases.sort_values(["n_missed", "transaction_id"], ascending=[False, True])

    # --- exploded (case, rule) hit lists ---
    hallucinated_rules = explode_rules(hallucinated_cases, "hallucinated_rules", "hallucinated_rule")
    missed_rules = explode_rules(missed_cases, "missed_rules", "missed_rule")

    paths = {
        "hallucinated_cases.csv": hallucinated_cases,
        "missed_cases.csv": missed_cases,
        "hallucinated_rules.csv": hallucinated_rules,
        "missed_rules.csv": missed_rules,
    }
    for name, frame in paths.items():
        frame.to_csv(os.path.join(out_dir, name), index=False)

    # --- console summary ---
    n = len(df)
    print(f"read {n} scored cases from {os.path.basename(results_path)}")
    print()
    print(f"cases with >=1 HALLUCINATED rule (AI yes, ML no): {len(hallucinated_cases):>6}  ({100*len(hallucinated_cases)/n:.1f}%)")
    print(f"cases with >=1 MISSED rule       (ML yes, AI no): {len(missed_cases):>6}  ({100*len(missed_cases)/n:.1f}%)")
    print(f"cases in BOTH lists                              : {len(both):>6}")
    print(f"cases in perfect agreement                       : {n - len(set(hallucinated_cases['transaction_id']) | set(missed_cases['transaction_id'])):>6}")
    print()
    print(f"individual hallucinated (case, rule) pairs: {len(hallucinated_rules)}")
    print(f"individual missed       (case, rule) pairs: {len(missed_rules)}")

    if len(hallucinated_rules):
        print("\nhallucinated rules, most frequent first:")
        print(hallucinated_rules["hallucinated_rule"].value_counts().to_string())
    if len(missed_rules):
        print("\nmissed rules, most frequent first:")
        print(missed_rules["missed_rule"].value_counts().to_string())

    print(f"\nwrote 4 files to {out_dir}:")
    for name in paths:
        print(f"  {name}")


if __name__ == "__main__":
    main()
