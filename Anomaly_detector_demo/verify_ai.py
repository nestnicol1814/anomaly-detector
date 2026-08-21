"""
verify_ai.py -- score the AI's rule flags against ground truth recomputed
from the base transaction dataset (plan steps 2+5).

Before first run, fill in:
  1. BASE_PATH / AI_PATH below
  2. BASE_KEY_COLS: the base columns holding company code and document number
  3. FIELD_MAP base column names in fraud_eval/rule_specs.py
Startup validation fails loudly until all three are done.

Outputs (next to BASE_PATH):
  ai_verdicts.csv       only FALSE_POSITIVE / FALSE_NEGATIVE / DATA_MISSING rows
                        (correct outcomes are kept as counts, not rows)
  ai_rule_scorecard.csv per rule: TP/FP/FN/TN/DATA_MISSING/UNCOMPUTABLE,
                        precision / recall / F1
"""
import os

import pandas as pd

from fraud_eval.loaders import load_AI_table, make_transaction_id
from fraud_eval.rule_specs import FIELD_MAP, base_columns_needed, validate_mapping
from fraud_eval.verifier import verify

# ---------------------------------------------------------------- fill these in
BASE_PATH = r"TODO"                     # base transaction dataset (.csv or .xlsx)
AI_PATH = r"TODO"                       # ADCMS export (.xlsx)
BASE_KEY_COLS = {"company_code": "TODO", "doc_nr": "TODO"}
# ------------------------------------------------------------------------------

CHUNK = 100_000                          # csv chunk size for the huge base file


def load_base(path, wanted_ids):
    """Read only needed columns, keep only wanted transaction_ids, return
    {transaction_id: row dict}. Duplicate base keys keep the FIRST row and
    are counted -- never silently multiplied into a join."""
    usecols = list(BASE_KEY_COLS.values()) + base_columns_needed()
    ext = os.path.splitext(path)[1].lower()

    def rows(df):
        df = df.copy()
        df["_id"] = [
            make_transaction_id(c, d)
            for c, d in zip(df[BASE_KEY_COLS["company_code"]], df[BASE_KEY_COLS["doc_nr"]])
        ]
        return df[df["_id"].isin(wanted_ids)]

    if ext == ".csv":
        parts = [rows(chunk) for chunk in
                 pd.read_csv(path, usecols=usecols, dtype=str, chunksize=CHUNK)]
        base = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    else:
        base = rows(pd.read_excel(path, usecols=usecols,
                                  dtype={c: str for c in BASE_KEY_COLS.values()}))

    n_dup = int(base["_id"].duplicated().sum())
    if n_dup:
        print(f"NOTE: {n_dup} duplicate base rows for already-seen keys -- keeping first per key")
    base = base.drop_duplicates(subset="_id", keep="first")
    return {r["_id"]: r for r in base.to_dict("records")}


def main():
    for name, val in (("BASE_PATH", BASE_PATH), ("AI_PATH", AI_PATH),
                      *((f"BASE_KEY_COLS[{k}]", v) for k, v in BASE_KEY_COLS.items())):
        if val == "TODO":
            raise SystemExit(f"{name} is still TODO -- fill it in at the top of verify_ai.py "
                             f"(and FIELD_MAP in fraud_eval/rule_specs.py)")

    ai_table, ai_report = load_AI_table(AI_PATH)
    print(ai_report.summary())

    base_lookup = load_base(BASE_PATH, set(ai_table))
    if base_lookup:
        sample_cols = next(iter(base_lookup.values())).keys()
        validate_mapping(sample_cols)          # dies here if FIELD_MAP is wrong

    verdict_rows, scorecard = verify(ai_table, base_lookup)

    out_dir = os.path.dirname(BASE_PATH)
    problems = [r for r in verdict_rows
                if r["outcome"] in ("FALSE_POSITIVE", "FALSE_NEGATIVE", "DATA_MISSING")]
    pd.DataFrame(problems).to_csv(os.path.join(out_dir, "ai_verdicts.csv"), index=False)
    card = pd.DataFrame(scorecard["per_rule"])
    card.to_csv(os.path.join(out_dir, "ai_rule_scorecard.csv"), index=False)

    print(f"\nscored {len(ai_table) - len(scorecard['no_base_data_cases'])} cases "
          f"({len(scorecard['no_base_data_cases'])} had NO base data row)")
    show = card[["rule", "TRUE_POSITIVE", "FALSE_POSITIVE", "FALSE_NEGATIVE",
                 "DATA_MISSING", "UNCOMPUTABLE", "precision", "recall", "f1"]]
    show = show.sort_values(["FALSE_POSITIVE", "FALSE_NEGATIVE"], ascending=False)
    print(show.to_string(index=False))
    print(f"\nwrote ai_verdicts.csv and ai_rule_scorecard.csv to {out_dir}")


if __name__ == "__main__":
    main()
