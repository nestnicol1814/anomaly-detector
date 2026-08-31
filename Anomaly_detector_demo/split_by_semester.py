"""
split_by_semester.py -- split one Excel file into two by calendar semester so
the halves fit in memory (H1 = Jan-Jun, H2 = Jul-Dec, by the given date column).

    python split_by_semester.py "path/to/file.xlsx" "[Posting Date]"

Writes next to the input:
    <name>_H1.xlsx    rows with month 1-6
    <name>_H2.xlsx    rows with month 7-12
    <name>_undated.xlsx   rows whose date failed to parse (only if any exist --
                          never silently dropped)

The date column name must match the file's header exactly (quote it if it has
spaces/brackets). All other columns are passed through untouched.
"""
import os
import sys

import pandas as pd


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    path, date_col = sys.argv[1], sys.argv[2]
    if not os.path.isfile(path):
        sys.exit(f"file not found: {path}")

    df = pd.read_excel(path)
    if date_col not in df.columns:
        sys.exit(f"column {date_col!r} not found. Columns are:\n  {list(df.columns)}")

    dates = pd.to_datetime(df[date_col], errors="coerce")
    h1 = df[dates.dt.month <= 6]
    h2 = df[dates.dt.month >= 7]
    undated = df[dates.isna()]

    stem, ext = os.path.splitext(path)
    outputs = [(f"{stem}_H1{ext}", h1), (f"{stem}_H2{ext}", h2)]
    if len(undated):
        outputs.append((f"{stem}_undated{ext}", undated))

    for out_path, frame in outputs:
        try:
            frame.to_excel(out_path, index=False)
        except PermissionError:
            sys.exit(f"Cannot write {out_path} -- close it in Excel and rerun.")

    print(f"read {len(df)} rows from {os.path.basename(path)} (date column: {date_col})")
    print(f"  H1 (Jan-Jun): {len(h1):>7} rows -> {os.path.basename(outputs[0][0])}")
    print(f"  H2 (Jul-Dec): {len(h2):>7} rows -> {os.path.basename(outputs[1][0])}")
    if len(undated):
        print(f"  undated:      {len(undated):>7} rows -> {os.path.basename(outputs[2][0])}"
              f"  (dates that failed to parse -- check these)")
    assert len(h1) + len(h2) + len(undated) == len(df), "row accounting mismatch"
    print("row accounting: OK (H1 + H2 + undated == total)")


if __name__ == "__main__":
    main()
