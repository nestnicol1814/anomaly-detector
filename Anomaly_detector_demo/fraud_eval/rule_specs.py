"""
Rule catalogue as data (plan step 1).

Every rule is a RuleSpec: which logical fields it needs and a predicate over
already-typed values. Predicates never parse or handle blanks -- the verifier's
resolve_fields() does that centrally and short-circuits to DATA_MISSING first.

Formulas transcribed from the ICCC system prompt's "COMPUTED FIELDS AND RULE
LOGIC" section. Where the prompt is ambiguous the choice is documented inline
and marked CONFIRM.

FIELD_MAP maps logical field names to the BASE dataset's column names.
The base column names are TODO until the real base extract's header row is
known -- validate_mapping() fails loudly on any TODO or missing column, so the
verifier cannot run against a half-filled mapping.
"""
import re
from dataclasses import dataclass


@dataclass
class RuleSpec:
    rule_id: str
    name: str
    requires: list                    # logical field names (keys of FIELD_MAP)
    predicate: object = None          # dict of typed values -> bool
    computable: bool = True
    reason_uncomputable: str = ""


def _is_weekend(d):
    return d.weekday() >= 5           # Mon=0 .. Sat=5, Sun=6


def word_match_ratio(a, b):
    """Shared-word ratio for R17 (entry user vs supplier name).
    CONFIRM definition: intersection over the smaller token set. The ICCC
    prompt only says 'shared word match ratio exceeds 75%'."""
    ta = set(re.findall(r"[a-z0-9]+", str(a).lower()))
    tb = set(re.findall(r"[a-z0-9]+", str(b).lower()))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


RULE_SPECS = {
    # CONFIRM: the ICCC prompt maps R01 (Record at weekend) to d_payment_date
    # and R02 (Payment at weekend) to d_entry_date -- which looks swapped
    # relative to the rule names. Transcribed as written; flip the two
    # `requires` lists if the business definition says otherwise.
    "R01": RuleSpec("R01", "Record at weekend",
                    ["payment_date"],
                    lambda v: _is_weekend(v["payment_date"])),
    "R02": RuleSpec("R02", "Payment at weekend",
                    ["entry_date"],
                    lambda v: _is_weekend(v["entry_date"])),
    "R03": RuleSpec("R03", "Less than 30 days between vendor creation and Non-PO",
                    ["entry_date", "vendor_create_date"],
                    lambda v: (v["entry_date"] - v["vendor_create_date"]).days < 30),
    "R04": RuleSpec("R04", "Less than 15 days between bank account change and Non-PO",
                    ["entry_date", "bank_change_date"],
                    lambda v: (v["entry_date"] - v["bank_change_date"]).days < 15),
    "R05": RuleSpec("R05", "Vendor without Non-PO in last two months", [],
                    computable=False,
                    reason_uncomputable="needs 2-month Non-PO history per supplier"),
    "R06": RuleSpec("R06", "Company Code + vendor cumulative amount above CHF 500K", [],
                    computable=False,
                    reason_uncomputable="needs cumulative amount per company+vendor; "
                                        "enable if base extract carries a cumulative field"),
    "R07": RuleSpec("R07", "Single record for supplier above CHF 100K",
                    ["value_custom"],
                    lambda v: v["value_custom"] > 100_000),
    "R08": RuleSpec("R08", "Single record for employee above CHF 10K",
                    ["value_custom", "vendor_group"],
                    lambda v: v["value_custom"] > 10_000 and v["vendor_group"] == "Z002"),
    "R09": RuleSpec("R09", "Supplier name starts with ZZ",
                    ["supplier_name"],
                    lambda v: v["supplier_name"].upper().startswith("ZZ")),
    "R13": RuleSpec("R13", "Bank in tax haven, not same country as vendor",
                    ["bank_ctry", "supplier_country", "bank_ctry_tax_haven"],
                    lambda v: v["bank_ctry"] != v["supplier_country"]
                              and v["bank_ctry_tax_haven"]),
    "R14": RuleSpec("R14", "Bank in tax haven, not same zone as vendor",
                    ["bank_zone", "vendor_zone", "bank_ctry_tax_haven"],
                    lambda v: v["bank_zone"] != v["vendor_zone"]
                              and v["bank_ctry_tax_haven"]),
    "R15": RuleSpec("R15", "Vendor and bank not in same zone",
                    ["bank_zone", "vendor_zone"],
                    lambda v: v["bank_zone"] != v["vendor_zone"]),
    "R16": RuleSpec("R16", "Bank in exotic/high-risk country, not same as vendor",
                    ["bank_ctry", "supplier_country", "bank_ctry_exotic_country"],
                    lambda v: v["bank_ctry"] != v["supplier_country"]
                              and v["bank_ctry_exotic_country"]),
    "R17": RuleSpec("R17", "User recorded Non-PO for own employee number",
                    ["entry_user", "supplier_name"],
                    lambda v: word_match_ratio(v["entry_user"], v["supplier_name"]) > 0.75),
    "R27": RuleSpec("R27", "Document created before vendor creation",
                    ["document_date", "vendor_create_date"],
                    lambda v: v["document_date"] < v["vendor_create_date"]),
}


# --------------------------------------------------------------------------
# Logical field -> base-data column. types: date | number | string | bool
# TODO: replace the TODO strings with the base extract's real column names.
# --------------------------------------------------------------------------
FIELD_MAP = {
    "entry_date":              {"col": "TODO", "type": "date"},
    "payment_date":            {"col": "TODO", "type": "date"},
    "document_date":           {"col": "TODO", "type": "date"},
    "vendor_create_date":      {"col": "TODO", "type": "date"},
    "bank_change_date":        {"col": "TODO", "type": "date"},
    "value_custom":            {"col": "TODO", "type": "number"},
    "vendor_group":            {"col": "TODO", "type": "string"},
    "supplier_name":           {"col": "TODO", "type": "string"},
    "entry_user":              {"col": "TODO", "type": "string"},
    "bank_ctry":               {"col": "TODO", "type": "string"},
    "supplier_country":        {"col": "TODO", "type": "string"},
    "bank_zone":               {"col": "TODO", "type": "string"},
    "vendor_zone":             {"col": "TODO", "type": "string"},
    "bank_ctry_tax_haven":     {"col": "TODO", "type": "bool"},
    "bank_ctry_exotic_country": {"col": "TODO", "type": "bool"},
}


def validate_mapping(columns, field_map=None, rules=None):
    """Fail loudly BEFORE any verdicts if the mapping is unfinished or points
    at columns the base data doesn't have. Only fields required by computable
    rules are enforced."""
    field_map = FIELD_MAP if field_map is None else field_map
    rules = RULE_SPECS if rules is None else rules
    problems = []
    needed = {f for spec in rules.values() if spec.computable for f in spec.requires}
    for logical in sorted(needed):
        entry = field_map.get(logical)
        if entry is None:
            problems.append(f"logical field {logical!r} missing from FIELD_MAP")
        elif entry["col"] == "TODO":
            problems.append(f"FIELD_MAP[{logical!r}] is still TODO")
        elif entry["col"] not in columns:
            problems.append(f"FIELD_MAP[{logical!r}] -> {entry['col']!r} not in base columns")
    if problems:
        raise ValueError("FIELD_MAP validation failed:\n  " + "\n  ".join(problems))


def base_columns_needed(field_map=None, rules=None):
    """The base columns the verifier actually reads (for usecols)."""
    field_map = FIELD_MAP if field_map is None else field_map
    rules = RULE_SPECS if rules is None else rules
    needed = {f for spec in rules.values() if spec.computable for f in spec.requires}
    return sorted({field_map[f]["col"] for f in needed if f in field_map})
