"""
make_verifier_fixtures.py -- prove the verdict engine on synthetic data before
it touches real data. Plants at least one case per outcome class and asserts
the engine returns exactly the expected verdict for each.

    python make_verifier_fixtures.py      -> prints PASS or dies on AssertionError
"""
import pandas as pd

from fraud_eval.verifier import verify

# Fixture field map: logical field -> fixture column (types as in production).
FIXTURE_FIELD_MAP = {
    "entry_date":              {"col": "ENTRY_DATE", "type": "date"},
    "payment_date":            {"col": "PAYMENT_DATE", "type": "date"},
    "document_date":           {"col": "DOC_DATE", "type": "date"},
    "vendor_create_date":      {"col": "VENDOR_CREATED", "type": "date"},
    "bank_change_date":        {"col": "BANK_CHANGED", "type": "date"},
    "value_custom":            {"col": "VALUE_CHF", "type": "number"},
    "vendor_group":            {"col": "VENDOR_GROUP", "type": "string"},
    "supplier_name":           {"col": "SUPPLIER_NAME", "type": "string"},
    "entry_user":              {"col": "ENTRY_USER", "type": "string"},
    "bank_ctry":               {"col": "BANK_CTRY", "type": "string"},
    "supplier_country":        {"col": "SUPPLIER_CTRY", "type": "string"},
    "bank_zone":               {"col": "BANK_ZONE", "type": "string"},
    "vendor_zone":             {"col": "VENDOR_ZONE", "type": "string"},
    "bank_ctry_tax_haven":     {"col": "TAX_HAVEN", "type": "bool"},
    "bank_ctry_exotic_country": {"col": "EXOTIC", "type": "bool"},
}

FULL_ROW = {  # a base row where every field is present and NO rule condition is met
    "ENTRY_DATE": "2026-03-16",       # Monday
    "PAYMENT_DATE": "2026-03-17",     # Tuesday
    "DOC_DATE": "2026-03-10",
    "VENDOR_CREATED": "2020-01-15",   # years old -> R03/R27 not met
    "BANK_CHANGED": "2024-06-01",     # long ago -> R04 not met
    "VALUE_CHF": "5000",
    "VENDOR_GROUP": "Z001",
    "SUPPLIER_NAME": "Acme Industrial Supplies",
    "ENTRY_USER": "jdoe",
    "BANK_CTRY": "CH", "SUPPLIER_CTRY": "CH",
    "BANK_ZONE": "EUR", "VENDOR_ZONE": "EUR",
    "TAX_HAVEN": "No", "EXOTIC": "No",
}


def row(**overrides):
    return {**FULL_ROW, **overrides}


def flags(**on):
    return {rid: on.get(rid, False) for rid in
            ["R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08", "R09",
             "R13", "R14", "R15", "R16", "R17", "R27"]}


# transaction_id -> (base row, ai flags, {rule: expected outcome})
CASES = {
    # R07 value threshold: all four confusion quadrants
    "T_TP": (row(VALUE_CHF="150000"), flags(R07=True),  {"R07": "TRUE_POSITIVE"}),
    "T_FP": (row(VALUE_CHF="50000"),  flags(R07=True),  {"R07": "FALSE_POSITIVE"}),
    "T_FN": (row(VALUE_CHF="150000"), flags(),          {"R07": "FALSE_NEGATIVE"}),
    "T_TN": (row(VALUE_CHF="50000"),  flags(),          {"R07": "TRUE_NEGATIVE"}),
    # R03 date arithmetic: 12 days -> met
    "T_R03": (row(VENDOR_CREATED="2026-03-04"), flags(), {"R03": "FALSE_NEGATIVE"}),
    # R27: document before vendor creation
    "T_R27": (row(VENDOR_CREATED="2026-03-12"), flags(R27=True), {"R27": "TRUE_POSITIVE",
                                                                   "R03": "FALSE_NEGATIVE"}),
    # R01 weekend: payment date on a Saturday (per ICCC prompt's field mapping)
    "T_R01": (row(PAYMENT_DATE="2026-03-14"), flags(), {"R01": "FALSE_NEGATIVE"}),
    # R09 name prefix
    "T_R09": (row(SUPPLIER_NAME="ZZ-Vendor Services"), flags(R09=True), {"R09": "TRUE_POSITIVE"}),
    # R13 geography + bool: Panama tax haven, vendor in CH
    "T_R13": (row(BANK_CTRY="PA", TAX_HAVEN="Yes"), flags(), {"R13": "FALSE_NEGATIVE",
                                                              "R16": "TRUE_NEGATIVE"}),
    # R15 zone mismatch without tax haven
    "T_R15": (row(BANK_ZONE="AMS"), flags(R15=True), {"R15": "TRUE_POSITIVE",
                                                      "R14": "TRUE_NEGATIVE"}),
    # R17 self-dealing: entry user's words inside supplier name
    "T_R17": (row(ENTRY_USER="Garcia Lopez", SUPPLIER_NAME="Garcia Lopez Consulting"),
              flags(), {"R17": "FALSE_NEGATIVE"}),
    # R08: needs value>10K AND group Z002
    "T_R08": (row(VALUE_CHF="15000", VENDOR_GROUP="Z002"), flags(), {"R08": "FALSE_NEGATIVE"}),
    # blank field -> DATA_MISSING regardless of flag
    "T_MISS": (row(BANK_CTRY=""), flags(R13=True), {"R13": "DATA_MISSING",
                                                    "R16": "DATA_MISSING",
                                                    "R15": "TRUE_NEGATIVE"}),
    # blank bool is missing, not False
    "T_BOOLMISS": (row(TAX_HAVEN=None), flags(), {"R13": "DATA_MISSING"}),
}

EXPECT_UNCOMPUTABLE = {"R05", "R06"}


def main():
    ai_table = {tid: {"ai_flags": f} for tid, (_, f, _) in CASES.items()}
    ai_table["T_NOBASE"] = {"ai_flags": flags()}          # case absent from base
    base_lookup = {tid: r for tid, (r, _, _) in CASES.items()}

    verdict_rows, scorecard = verify(ai_table, base_lookup, field_map=FIXTURE_FIELD_MAP)
    by = {(r["transaction_id"], r["rule"]): r["outcome"] for r in verdict_rows}

    failures = []
    for tid, (_, _, expected) in CASES.items():
        for rid, want in expected.items():
            got = by.get((tid, rid))
            if got != want:
                failures.append(f"{tid}/{rid}: expected {want}, got {got}")
    for rid in EXPECT_UNCOMPUTABLE:
        got = by.get(("T_TP", rid))
        if got != "UNCOMPUTABLE":
            failures.append(f"T_TP/{rid}: expected UNCOMPUTABLE, got {got}")
    if scorecard["no_base_data_cases"] != ["T_NOBASE"]:
        failures.append(f"no_base_data_cases: {scorecard['no_base_data_cases']}")

    if failures:
        print("FAIL")
        for f in failures:
            print(" ", f)
        raise SystemExit(1)
    n_checked = sum(len(e) for _, _, e in CASES.values()) + len(EXPECT_UNCOMPUTABLE) + 1
    print(f"PASS -- {n_checked} planted outcomes all verified "
          f"({len(verdict_rows)} verdicts produced)")


if __name__ == "__main__":
    main()
