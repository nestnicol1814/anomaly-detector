"""
diagnose_overlap.py -- WHY don't the two files overlap more?

diagnose_rows.py answered "how many match". This answers "what do the
non-matching rows look like" so we can tell a real coverage difference
(different date range / scope) from a hidden join-key problem.

    python diagnose_overlap.py "path/to/Report Case Extract.xlsx" "path/to/ADCMS Case Rules 2026 Export.xlsx"

Read-only.
"""
import sys
import pandas as pd
from fraud_eval.loaders import make_transaction_id, normalize_company_code, normalize_doc_nr

ML_CC, ML_DOC = "[Company Code]", "[Document Nr]"
AI_CC, AI_DOC = "COMPANY_CODE", "DOCUMENT_NR"


def hr(t):
    print("\n" + "=" * 90 + "\n" + t + "\n" + "=" * 90)


def load(path, cc, doc):
    df = pd.read_excel(path, dtype={cc: str, doc: str})
    df["_cc"] = df[cc].map(normalize_company_code)
    df["_doc"] = df[doc].map(normalize_doc_nr)
    df["_id"] = [make_transaction_id(a, b) for a, b in zip(df[cc], df[doc])]
    return df


def main():
    ml_path, ai_path = sys.argv[1], sys.argv[2]
    ml = load(ml_path, ML_CC, ML_DOC)
    ai = load(ai_path, AI_CC, AI_DOC)

    ml_ids, ai_ids = set(ml["_id"].dropna()), set(ai["_id"].dropna())
    both = ml_ids & ai_ids
    ml_only, ai_only = ml_ids - ai_ids, ai_ids - ml_ids

    hr("OVERLAP")
    print(f"ML unique ids: {len(ml_ids)}   AI unique ids: {len(ai_ids)}")
    print(f"in BOTH: {len(both)}   ML-only: {len(ml_only)}   AI-only: {len(ai_only)}")

    # --- 1. Do the two files even cover the same company codes? ---
    hr("1. COMPANY CODE COVERAGE  (does each file contain the same set of company codes?)")
    ml_cc, ai_cc = set(ml["_cc"].dropna()), set(ai["_cc"].dropna())
    print(f"company codes in ML: {len(ml_cc)}   in AI: {len(ai_cc)}   shared: {len(ml_cc & ai_cc)}")
    print(f"codes ONLY in ML ({len(ml_cc - ai_cc)}): {sorted(ml_cc - ai_cc)[:20]}")
    print(f"codes ONLY in AI ({len(ai_cc - ml_cc)}): {sorted(ai_cc - ml_cc)[:20]}")
    # how many ML rows belong to a company code the AI file doesn't have at all?
    ml_rows_no_ai_cc = ml[~ml["_cc"].isin(ai_cc)]
    ai_rows_no_ml_cc = ai[~ai["_cc"].isin(ml_cc)]
    print(f"ML rows whose company code is absent from AI file: {len(ml_rows_no_ai_cc)}")
    print(f"AI rows whose company code is absent from ML file: {len(ai_rows_no_ml_cc)}")

    # --- 2. Within SHARED company codes, how well do doc numbers overlap? ---
    hr("2. PER-COMPANY-CODE MATCH RATE (only codes present in both files)")
    rows = []
    for cc in sorted(ml_cc & ai_cc):
        m = set(ml.loc[ml["_cc"] == cc, "_id"].dropna())
        a = set(ai.loc[ai["_cc"] == cc, "_id"].dropna())
        rows.append((cc, len(m), len(a), len(m & a)))
    df = pd.DataFrame(rows, columns=["cc", "ml_ids", "ai_ids", "matched"])
    df["ml_match_%"] = (100 * df["matched"] / df["ml_ids"]).round(1)
    df = df.sort_values("ml_ids", ascending=False)
    print(df.head(25).to_string(index=False))
    print(f"... {len(df)} shared company codes total")
    zero = df[df["matched"] == 0]
    print(f"\nshared codes with ZERO matches: {len(zero)}  -> {sorted(zero['cc'])[:20]}")
    print("(a code present in both files with 0 matched doc numbers = a formatting")
    print(" difference in doc numbers for that code, OR different scope/date range)")

    # --- 3. Doc number shape: are the two files describing the same kind of number? ---
    hr("3. DOC NUMBER SHAPE  (length distribution after normalization)")
    for label, d in (("ML", ml), ("AI", ai)):
        lens = d["_doc"].dropna().str.len().value_counts().sort_index()
        print(f"{label}: {dict(lens)}")
    print("If ML and AI have different dominant lengths, they are not the same field.")

    # --- 4. Side-by-side: for a shared company code with poor match, show raw values ---
    hr("4. RAW SAMPLES from a poorly-matching shared company code")
    poor = df[(df["matched"] < df["ml_ids"] * 0.5) & (df["ml_ids"] >= 20)].head(1)
    if len(poor):
        cc = poor.iloc[0]["cc"]
        print(f"company code {cc!r}")
        print(" ML raw [Document Nr] samples :", ml.loc[ml["_cc"] == cc, ML_DOC].astype(str).head(8).tolist())
        print(" AI raw DOCUMENT_NR samples   :", ai.loc[ai["_cc"] == cc, AI_DOC].astype(str).head(8).tolist())
        print(" ML normalized doc            :", ml.loc[ml["_cc"] == cc, "_doc"].head(8).tolist())
        print(" AI normalized doc            :", ai.loc[ai["_cc"] == cc, "_doc"].head(8).tolist())
    else:
        print("no shared company code with <50% match and >=20 rows -- overlap is limited by scope, not format")

    # --- 5. Any other columns that could be the real key? ---
    hr("5. COLUMNS AVAILABLE (is there a better join key than company_code+doc_nr?)")
    print("ML columns:", list(ml.columns[:-3]))
    print("AI columns:", [c for c in ai.columns[:-3] if not c.startswith("R")][:30], "... + rule cols")


if __name__ == "__main__":
    main()
