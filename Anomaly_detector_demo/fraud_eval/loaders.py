"""
File loaders for the two input datasets:
  - the ML rule-trigger table (Excel) with comma-separated rule markers
  - the AI rule table (Excel) with binary rule columns (R01-R27)

Row-loss safeguards (see diagnose_rows.py for the audit that motivated them):

  1. Key columns are read with dtype=str so pandas can never turn a document
     number into a float ("1234567.0") or strip leading zeros from a company
     code ("0100" -> 100). Either would make the same transaction produce a
     different id in each file and silently fail the merge.
  2. Both loaders build the join key through ONE shared function
     (make_transaction_id) so the two files can't drift apart.
  3. Duplicate keys are NOT silently overwritten. Every loader returns a
     LoadReport alongside the data with raw / blank / duplicate / kept counts,
     and keeps the duplicate rows so you can inspect them.

Both raise a clear ValueError naming the offending file/row rather than
failing with a bare KeyError deep in some other function.
"""
import os
import warnings
from dataclasses import dataclass, field

import pandas as pd

from .rules import RULE_FLAGS

warnings.filterwarnings("ignore")

_MISSING_TOKENS = {"", "nan", "none", "nat", "null"}


# ---------------------------------------------------------------------------
# Shared key handling
# ---------------------------------------------------------------------------

def normalize_key(value):
    """Turn a raw cell into a canonical string key, or None if it's missing.

    - NaN / blank / 'nan' / 'None' -> None
    - trailing '.0' from float-ified integers is removed
    - surrounding whitespace is stripped
    Leading zeros are preserved because the columns are read as text.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    if s.lower() in _MISSING_TOKENS:
        return None
    if s.endswith(".0") and s[:-2].lstrip("-").isdigit():
        s = s[:-2]
    return s


# Zero-pad purely-numeric company codes to this width so '100' and '0100'
# match. OFF by default: it only helps when the two files store the SAME code
# at different widths, and it HURTS if it transforms one file's codes and not
# the other's. Run diagnose_rows.py first -- turn this on (e.g. 4) only if the
# "sample constructed ids" show a leading-zero mismatch between the files.
COMPANY_CODE_WIDTH = None


def normalize_company_code(value, width=COMPANY_CODE_WIDTH):
    """Company codes need one extra step beyond normalize_key: if the source
    file stored them as NUMBERS, Excel has already thrown away leading zeros
    ('0100' -> 100) before Python ever sees the cell. Reading as text can't
    undo that. So purely-numeric codes are zero-padded to a fixed width, which
    makes '100', '0100', and 100.0 all collapse to '0100' on BOTH sides."""
    s = normalize_key(value)
    if s is None:
        return None
    if width and s.isdigit() and len(s) < width:
        s = s.zfill(width)
    return s


def normalize_doc_nr(value):
    """Document numbers: the AI export stores them as TEXT with a leading zero
    ('0510001617') while the ML export stores them as numbers ('510001617').
    Confirmed by diagnose_rows.py on the real files: this single mismatch was
    the join-key failure. Reading the AI column as int64 used to strip the
    zero by accident (which is why ~10k matched before dtype=str); we now
    strip leading zeros from purely-numeric doc numbers deliberately, on BOTH
    sides, so both files build the same key."""
    s = normalize_key(value)
    if s is None:
        return None
    if s.isdigit():
        s = s.lstrip("0") or "0"
    return s


def make_transaction_id(company_code, doc_nr):
    """The ONE place the join key is built. Returns None if either part is missing."""
    cc = normalize_company_code(company_code)
    doc = normalize_doc_nr(doc_nr)
    if cc is None or doc is None:
        return None
    return f"{cc}_{doc}"


@dataclass
class LoadReport:
    """Row accounting for one loaded file. Printed by AnomalyEval.print_summary."""
    path: str
    n_raw: int = 0            # rows pandas read
    n_blank_key: int = 0      # rows dropped because company code or doc nr was missing
    n_duplicate_rows: int = 0 # rows beyond the first for a repeated key
    n_kept: int = 0           # unique keys that made it into the table
    duplicates: dict = field(default_factory=dict)  # key -> list of extra row dicts
    blank_rows: list = field(default_factory=list)  # first few offending row numbers

    def summary(self):
        return (f"{os.path.basename(self.path)}: {self.n_raw} rows -> "
                f"{self.n_blank_key} blank-key dropped, "
                f"{self.n_duplicate_rows} duplicate rows collapsed, "
                f"{self.n_kept} unique transactions kept")


def _read_excel_text_keys(path, key_cols, label):
    if not os.path.isfile(path):
        raise ValueError(f"{label} not found: {path}")
    try:
        # dtype=str on the key columns is the fix for float/leading-zero drift.
        df = pd.read_excel(path, dtype={c: str for c in key_cols})
    except Exception as e:
        raise ValueError(f"Failed to read {label} {path}: {e}")
    missing = set(key_cols) - set(df.columns)
    if missing:
        raise ValueError(f"{label} {path} is missing required column(s): {sorted(missing)}")
    return df


def _cell(row, col):
    v = row.get(col, "")
    return "" if v is None or (isinstance(v, float) and pd.isna(v)) else str(v).strip()


# ---------------------------------------------------------------------------
# ML table
# ---------------------------------------------------------------------------

def load_ml_table(excel_path, on_duplicate="last"):
    """Load ML table (Excel) with a comma-separated [Rule Marker] column.

    Expected columns: [Company Code], [Document Nr], [Supplier Nr], [Supplier name], [Rule Marker]
    Returns (table, report):
        table  = {transaction_id: {"ml_decision": str, "ml_flags": {rule_id: bool}, "metadata": {...}}}
        report = LoadReport with row accounting

    on_duplicate: what to keep when the same transaction_id appears more than once
        "last"  -> keep the last row (previous behaviour, now counted instead of silent)
        "first" -> keep the first row
        "union" -> OR the rule flags across all rows for that key (a document
                   with several rule-hit rows becomes one record with all its rules)
        "error" -> raise
    """
    df = _read_excel_text_keys(excel_path, ["[Company Code]", "[Document Nr]"], "ML table")
    if "[Rule Marker]" not in df.columns:
        raise ValueError(f"ML table {excel_path} is missing required column(s): ['[Rule Marker]']")

    table, report = {}, LoadReport(path=excel_path, n_raw=len(df))

    for idx, row in df.iterrows():
        transaction_id = make_transaction_id(row.get("[Company Code]"), row.get("[Document Nr]"))
        if transaction_id is None:
            report.n_blank_key += 1
            if len(report.blank_rows) < 10:
                report.blank_rows.append(idx + 2)
            continue

        triggered = {r.strip().upper() for r in _cell(row, "[Rule Marker]").split(",") if r.strip()}
        unknown = triggered - set(RULE_FLAGS)
        if unknown:
            raise ValueError(
                f"ML table {excel_path}, row {idx + 2}: unknown rule id(s) {sorted(unknown)} "
                f"in [Rule Marker] -- not in fraud_eval.rules.RULE_FLAGS"
            )
        entry = {
            "ml_decision": "High",
            "ml_flags": {rid: rid in triggered for rid in RULE_FLAGS},
            "metadata": {
                "company_code": normalize_company_code(row.get("[Company Code]")),
                "document_nr": normalize_doc_nr(row.get("[Document Nr]")),
                "supplier_nr": _cell(row, "[Supplier Nr]"),
                "supplier_name": _cell(row, "[Supplier name]"),
                "source_row": idx + 2,
            },
        }
        _insert(table, report, transaction_id, entry, "ml_flags", on_duplicate, excel_path, idx + 2)

    report.n_kept = len(table)
    if not table:
        raise ValueError(f"ML table {excel_path} has a header but no usable data rows")
    return table, report


# ---------------------------------------------------------------------------
# AI table
# ---------------------------------------------------------------------------

def load_AI_table(excel_path, on_duplicate="last"):
    """Load AI table (Excel) with binary rule columns (R01-R27).

    Expected columns: COMPANY_CODE, DOCUMENT_NR, SUPPLIER_NR, COMPANY_NAME, R01, ..., R27
    Returns (table, report):
        table  = {transaction_id: {"report_text": str, "ai_flags": {rule_id: bool}, "metadata": {...}}}
        report = LoadReport with row accounting
    on_duplicate: see load_ml_table.
    """
    df = _read_excel_text_keys(excel_path, ["COMPANY_CODE", "DOCUMENT_NR"], "AI table")

    rule_cols = [rid for rid in RULE_FLAGS if rid in df.columns]
    if not rule_cols:
        raise ValueError(
            f"AI table {excel_path} has no recognized rule columns "
            f"(expected some of {sorted(RULE_FLAGS)}); found {list(df.columns)}"
        )

    table, report = {}, LoadReport(path=excel_path, n_raw=len(df))

    for idx, row in df.iterrows():
        transaction_id = make_transaction_id(row.get("COMPANY_CODE"), row.get("DOCUMENT_NR"))
        if transaction_id is None:
            report.n_blank_key += 1
            if len(report.blank_rows) < 10:
                report.blank_rows.append(idx + 2)
            continue

        flags = {
            rid: _cell(row, rid).lower() in ("true", "1", "1.0", "yes", "y", "t")
            for rid in rule_cols
        }
        entry = {
            "report_text": (f"Company: {normalize_company_code(row.get('COMPANY_CODE'))}, "
                            f"Doc: {normalize_doc_nr(row.get('DOCUMENT_NR'))}, "
                            f"Supplier: {_cell(row, 'COMPANY_NAME')}"),
            "ai_flags": flags,
            "metadata": {
                "company_code": normalize_company_code(row.get("COMPANY_CODE")),
                "document_nr": normalize_doc_nr(row.get("DOCUMENT_NR")),
                "supplier_nr": _cell(row, "SUPPLIER_NR"),
                "supplier_name": _cell(row, "COMPANY_NAME"),
                "source_row": idx + 2,
            },
        }
        _insert(table, report, transaction_id, entry, "ai_flags", on_duplicate, excel_path, idx + 2)

    report.n_kept = len(table)
    if not table:
        raise ValueError(f"AI table {excel_path} has a header but no usable data rows")
    return table, report


# ---------------------------------------------------------------------------
# Duplicate policy (shared)
# ---------------------------------------------------------------------------

def _insert(table, report, key, entry, flags_field, on_duplicate, path, row_num):
    if key not in table:
        table[key] = entry
        return

    report.n_duplicate_rows += 1
    report.duplicates.setdefault(key, []).append(entry)

    if on_duplicate == "error":
        raise ValueError(f"{path}, row {row_num}: duplicate transaction_id {key!r}")
    elif on_duplicate == "first":
        return
    elif on_duplicate == "last":
        table[key] = entry
    elif on_duplicate == "union":
        merged = table[key]
        merged[flags_field] = {
            rid: merged[flags_field].get(rid, False) or entry[flags_field].get(rid, False)
            for rid in set(merged[flags_field]) | set(entry[flags_field])
        }
    else:
        raise ValueError(f"on_duplicate must be one of last/first/union/error, got {on_duplicate!r}")
