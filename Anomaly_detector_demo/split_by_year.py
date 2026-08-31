"""
split_by_year.py -- split one Excel file into one file per YEAR of a date
column (default: D_POSTING_DATE).

    python split_by_year.py "path/to/file.xlsx"
    python split_by_year.py "path/to/file.xlsx" "[Posting Date]"   (other column)

Writes next to the input, one file per year found in the data:
    <name>_2020.xlsx, <name>_2021.xlsx, ... (whatever years exist)
    <name>_undated.xlsx   rows whose date failed to parse (only if any --
                          never silently dropped)

All other columns pass through untouched.
"""
import os
import sys

import pandas as pd

DEFAULT_DATE_COL = "D_POSTING_DATE"


def main():
    if len(sys.argv) not in (2, 3):
        print(__doc__)
        sys.exit(1)
    path = sys.argv[1]
    date_col = sys.argv[2] if len(sys.argv) == 3 else DEFAULT_DATE_COL
    if not os.path.isfile(path):
        sys.exit(f"file not found: {path}")

    df = pd.read_excel(path)
    if date_col not in df.columns:
        sys.exit(f"column {date_col!r} not found. Columns are:\n  {list(df.columns)}")

    dates = pd.to_datetime(df[date_col], errors="coerce")
    undated = df[dates.isna()]
    stem, ext = os.path.splitext(path)

    print(f"read {len(df)} rows from {os.path.basename(path)} (date column: {date_col})")
    written = 0
    for year in sorted(dates.dropna().dt.year.unique()):
        part = df[dates.dt.year == year]
        out_path = f"{stem}_{int(year)}{ext}"
        try:
            part.to_excel(out_path, index=False)
        except PermissionError:
            sys.exit(f"Cannot write {out_path} -- close it in Excel and rerun.")
        print(f"  {int(year)}: {len(part):>7} rows -> {os.path.basename(out_path)}")
        written += len(part)

    if len(undated):
        out_path = f"{stem}_undated{ext}"
        undated.to_excel(out_path, index=False)
        print(f"  undated: {len(undated):>4} rows -> {os.path.basename(out_path)}"
              f"  (dates that failed to parse -- check these)")
        written += len(undated)

    assert written == len(df), "row accounting mismatch"
    print("row accounting: OK (per-year files + undated == total)")


if __name__ == "__main__":
    main()
