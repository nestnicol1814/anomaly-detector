"""
diagnose_rows.py -- find exactly where rows disappear between the two raw
Excel files and the final ML-vs-AI merge.

Usage:
    python diagnose_rows.py "path/to/Report Case Extract.xlsx" "path/to/ADCMS Case Rules 2026 Export.xlsx"

Prints, per file:
  1. raw row count
  2. rows with a blank/NaN key column
  3. duplicate join-key rows (row count vs unique key count) with examples
  4. the pandas dtype of each key column (numeric vs text is the usual culprit)
  5. sample of the constructed transaction_ids
Then compares the two files:
  6. match count under the CURRENT id construction (str(x).strip())
  7. match count under a NORMALIZED construction (dtype=str, strip trailing
     ".0", strip whitespace) -- if this is higher, the join key was the problem
  8. sample of ids that match only after normalization, and ids that never match

Nothing is modified. Read-only.
"""
import sys
import pandas as pd

ML_CC, ML_DOC = "[Company Code]", "[Document Nr]"
AI_CC, AI_DOC = "COMPANY_CODE", "DOCUMENT_NR"


def hr(title):
    print("\n" + "=" * 90)
    print(title)
    print("=" * 90)


# Use the SAME normalization the fixed loaders use, so "normalized match count"
# below is exactly what fraud_eval will produce -- not a separate guess.
from fraud_eval.loaders import normalize_key, normalize_company_code


def audit_file(label, path, cc_col, doc_col):
    hr(f"{label}: {path}")

    # --- as the loaders currently read it (pandas infers dtypes) ---
    df_inferred = pd.read_excel(path)
    # --- as it should be read (keys forced to text, no float inference) ---
    df_str = pd.read_excel(path, dtype={cc_col: str, doc_col: str})

    n_raw = len(df_inferred)
    print(f"1. raw rows read by pandas:            {n_raw}")

    for col in (cc_col, doc_col):
        if col not in df_inferred.columns:
            print(f"   !! column {col!r} NOT FOUND. Columns are: {list(df_inferred.columns)}")
            return None
    print(f"4. dtype (inferred read)  {cc_col!r}: {df_inferred[cc_col].dtype}   "
          f"{doc_col!r}: {df_inferred[doc_col].dtype}")
    if str(df_inferred[cc_col].dtype).startswith(("float", "int")) or \
       str(df_inferred[doc_col].dtype).startswith(("float", "int")):
        print("   !! at least one key column was read as NUMERIC. Leading zeros are lost and/or")
        print("      integers become floats ('1234567.0'). This breaks the join against the other file.")

    blank_cc = df_str[cc_col].isna() | (df_str[cc_col].astype(str).str.strip() == "")
    blank_doc = df_str[doc_col].isna() | (df_str[doc_col].astype(str).str.strip() == "")
    n_blank = int((blank_cc | blank_doc).sum())
    print(f"2. rows with blank company code or doc nr: {n_blank}")
    if n_blank:
        print("   examples:")
        print(df_str[blank_cc | blank_doc].head(5).to_string())

    # ids as the CURRENT loader builds them
    cur_ids = (df_inferred[cc_col].astype(str).str.strip() + "_" +
               df_inferred[doc_col].astype(str).str.strip())
    # ids under the NORMALIZED construction
    norm_ids = (df_str[cc_col].map(normalize_company_code).fillna("<MISSING>") + "_" +
                df_str[doc_col].map(normalize_key).fillna("<MISSING>"))

    n_unique_cur = cur_ids.nunique()
    n_unique_norm = norm_ids.nunique()
    n_dup_rows_cur = n_raw - n_unique_cur
    print(f"3. unique join keys (current construction):  {n_unique_cur}  "
          f"-> {n_dup_rows_cur} rows collapse as duplicates in the loader's dict")
    print(f"   unique join keys (normalized):           {n_unique_norm}")
    if n_dup_rows_cur:
        dup_keys = cur_ids[cur_ids.duplicated(keep=False)]
        top = dup_keys.value_counts().head(8)
        print("   most-repeated keys (key -> row count):")
        for k, c in top.items():
            print(f"      {k!r}: {c}")
        print("   NOTE: the loader keeps only the LAST row for each of these keys.")

    print("5. sample constructed ids (current | normalized):")
    for a, b in list(zip(cur_ids.head(6), norm_ids.head(6))):
        flag = "" if a == b else "   <-- differs"
        print(f"      {a!r:<35} | {b!r}{flag}")

    return {
        "n_raw": n_raw,
        "cur_ids": set(cur_ids),
        "norm_ids": set(norm_ids),
        "cur_series": cur_ids,
        "norm_series": norm_ids,
    }


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    ml_path, ai_path = sys.argv[1], sys.argv[2]

    ml = audit_file("ML TABLE", ml_path, ML_CC, ML_DOC)
    ai = audit_file("AI TABLE", ai_path, AI_CC, AI_DOC)
    if ml is None or ai is None:
        sys.exit(1)

    hr("MERGE: how many ids line up between the two files")
    cur_match = ml["cur_ids"] & ai["cur_ids"]
    norm_match = ml["norm_ids"] & ai["norm_ids"]
    print(f"6. matched under CURRENT construction:     {len(cur_match)}")
    print(f"7. matched under NORMALIZED construction:  {len(norm_match)}")
    gained = norm_match - cur_match
    if gained:
        print(f"   -> normalization RECOVERS {len(gained)} ids that currently fail to match.")
        print("   examples recovered:")
        for x in sorted(gained)[:8]:
            print(f"      {x!r}")
    else:
        print("   -> normalization does not change the match count; the join key is consistent.")

    ml_only = ml["norm_ids"] - ai["norm_ids"]
    ai_only = ai["norm_ids"] - ml["norm_ids"]
    print(f"8. after normalization, ids ONLY in ML: {len(ml_only)}   ONLY in AI: {len(ai_only)}")
    if ml_only:
        print("   ML-only examples:", sorted(ml_only)[:6])
    if ai_only:
        print("   AI-only examples:", sorted(ai_only)[:6])

    hr("SUMMARY: where the rows go")
    print(f"ML: {ml['n_raw']} rows -> {len(ml['cur_ids'])} unique keys (loader dict)  "
          f"-> {len(cur_match)} survive merge (current)  /  {len(norm_match)} (normalized)")
    print(f"AI: {ai['n_raw']} rows -> {len(ai['cur_ids'])} unique keys (loader dict)  "
          f"-> {len(cur_match)} survive merge (current)  /  {len(norm_match)} (normalized)")


if __name__ == "__main__":
    main()
