"""
Build two small Excel files that deliberately reproduce every row-loss mode
the real files are suspected of having, so the loaders + diagnose_rows.py can
be tested without confidential data.

    python make_test_fixtures.py     -> writes test_ml.xlsx and test_ai.xlsx

Loss modes planted:
  - ML stores Document Nr as TEXT ("5000123") but AI stores it as a NUMBER
    (5000123) -- normalize_doc_nr must reconcile them.
  - SID/FISCAL_YEAR text in ML vs numeric in AI -- same reconciliation.
  - The same key appears on 3 rows in ML (one row per rule hit).
  - One AI row has a blank COMPANY_CODE.
  - One transaction exists only in ML, one only in AI.
"""
import pandas as pd

ml = pd.DataFrame({
    "[Company Code]": ["AE10", "AE10", "AE10", "BE20", "BE20", "CE30", "CE30"],
    "[Document Nr]":  ["5000123", "5000123", "5000123", "5000124", "5000125", "5000126", "5000199"],
    "[Fiscal year]":  ["2026", "2026", "2026", "2026", "2026", "2026", "2026"],
    "[Supplier Nr]":  ["V1", "V1", "V1", "V2", "V3", "V4", "V9"],
    "[SID]":          ["901", "901", "901", "902", "903", "904", "909"],   # text here, number in AI
    "[Item]":         ["001", "001", "001", "001", "002", "001", "001"],   # text "001" -> must match AI numeric 1
    "[Data Marker]":  ["M1", "M1", "M1", "M0", "M0", "M0", "M0"],
    "[Supplier name]": ["Acme", "Acme", "Acme", "Beta", "Gamma", "Delta", "OnlyInML"],
    "[Rule Marker]":  ["R03", "R07", "R14", "", "R06", "R01,R02", "R09"],
})
# force text storage in Excel for the ML file
with pd.ExcelWriter("test_ml.xlsx", engine="openpyxl") as w:
    ml.to_excel(w, index=False)

ai = pd.DataFrame({
    "COMPANY_CODE": ["AE10", "BE20", "BE20", "CE30", None, "DE40"],   # alphanumeric like real data; one blank
    "DOCUMENT_NR":  [5000123, 5000124, 5000125, 5000126, 5000127, 5000200],  # numeric
    "FISCAL_YEAR":  [2026, 2026, 2026, 2026, 2026, 2026],     # numeric vs ML's text
    "SUPPLIER_NR":  ["V1", "V2", "V3", "V4", "V5", "V8"],
    "SID":          [901, 902, 903, 904, 905, 908],           # numeric vs ML's text
    "ITEM":         [1, 1, 2, 1, 1, 1],                       # numeric 1 vs ML's text "001"
    "DATA_MARKER":  ["M1", "M0", "M0", "M0", "M0", "M0"],
    "COMPANY_NAME": ["Acme", "Beta", "Gamma", "Delta", "Blank", "OnlyInAI"],
    "R01": [0, 0, 0, 1, 0, 0],
    "R02": [0, 0, 0, 1, 0, 0],
    "R03": [1, 0, 0, 0, 0, 0],
    "R06": [0, 0, 1, 0, 0, 0],
    "R07": [1, 0, 0, 0, 0, 0],
    "R09": [0, 0, 0, 0, 0, 1],
    "R13": [1, 0, 0, 0, 0, 0],
    "R14": [0, 0, 0, 0, 0, 0],
})
ai.to_excel("test_ai.xlsx", index=False)
print("wrote test_ml.xlsx (7 rows) and test_ai.xlsx (6 rows)")
