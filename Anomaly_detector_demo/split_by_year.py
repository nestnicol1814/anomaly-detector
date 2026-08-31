"""
split_by_year.py -- split one Excel file into one file per FISCAL_YEAR value.

    python split_by_year.py "path/to/file.xlsx"
    python split_by_year.py "path/to/file.xlsx" "[Fiscal year]"   (other column)

No date parsing: rows are grouped by the raw value in the column (e.g. 2020,
2021, ...). Writes next to the input, one file per distinct year found:
    <name>_2020.xlsx, <name>_2021.xlsx, ...
    <name>_blank.xlsx   rows with an empty year cell (only if any exist --
                        never silently dropped)

All other columns pass through untouched.
"""
import os
import sys

import pandas as pd

DEFAULT_YEAR_COL = "FISCAL_YEAR"


def year_label(value):
    """Raw cell -> clean label: strips whitespace and a float '.0' tail
    (2024.0 -> '2024'). Returns None for blank cells."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    s = str(value).strip()
    if not s or s.lower() in ("nan", "none"):
        return None
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s


def main():
    if len(sys.argv) not in (2, 3):
        print(__doc__)
        sys.exit(1)
    path = sys.argv[1]
    year_col = sys.argv[2] if len(sys.argv) == 3 else DEFAULT_YEAR_COL
    if not os.path.isfile(path):
        sys.exit(f"file not found: {path}")

    df = pd.read_excel(path)
    if year_col not in df.columns:
        sys.exit(f"column {year_col!r} not found. Columns are:\n  {list(df.columns)}")

    labels = df[year_col].map(year_label)
    stem, ext = os.path.splitext(path)

    print(f"read {len(df)} rows from {os.path.basename(path)} (year column: {year_col})")
    written = 0
    for year in sorted(labels.dropna().unique()):
        part = df[labels == year]
        out_path = f"{stem}_{year}{ext}"
        try:
            part.to_excel(out_path, index=False)
        except PermissionError:
            sys.exit(f"Cannot write {out_path} -- close it in Excel and rerun.")
        print(f"  {year}: {len(part):>7} rows -> {os.path.basename(out_path)}")
        written += len(part)

    blank = df[labels.isna()]
    if len(blank):
        out_path = f"{stem}_blank{ext}"
        blank.to_excel(out_path, index=False)
        print(f"  blank year: {len(blank):>4} rows -> {os.path.basename(out_path)}")
        written += len(blank)

    assert written == len(df), "row accounting mismatch"
    print("row accounting: OK (per-year files + blank == total)")


if __name__ == "__main__":
    main()
