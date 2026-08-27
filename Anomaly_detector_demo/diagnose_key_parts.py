"""
diagnose_key_parts.py -- after extending the merge key, WHICH segment is
breaking former matches?

For every ML-only key that shares company_code + doc_nr with at least one
AI-only key, finds the closest AI counterpart and tallies which of the extra
segments (fiscal_year, supplier_nr, sid, item, data_marker) differ. A segment
that dominates the tally is the one wrongly splitting real matches (e.g. the
two systems record data_marker differently, or one export is document-level
while the other is line-item level).

    python diagnose_key_parts.py "path/to/ML extract.xlsx" "path/to/AI export.xlsx"

Read-only.
"""
import sys
from collections import Counter, defaultdict

from fraud_eval.loaders import load_ml_table, load_AI_table

SEGMENTS = ["fiscal_year", "supplier_nr", "sid", "item", "data_marker"]


def parts_of(meta):
    return tuple((meta.get(s) or "") for s in SEGMENTS)


def index_by_prefix(table):
    idx = defaultdict(list)
    for key, entry in table.items():
        m = entry["metadata"]
        idx[(m.get("company_code"), m.get("document_nr"))].append((key, parts_of(m)))
    return idx


def main():
    if len(sys.argv) != 3:
        print("usage: python diagnose_key_parts.py <ML extract.xlsx> <AI export.xlsx>")
        sys.exit(1)

    ml_table, ml_rep = load_ml_table(sys.argv[1])
    ai_table, ai_rep = load_AI_table(sys.argv[2])
    print(ml_rep.summary())
    print(ai_rep.summary())

    matched = set(ml_table) & set(ai_table)
    ml_only = set(ml_table) - matched
    ai_only = set(ai_table) - matched
    print(f"\nmatched: {len(matched)}   ML-only: {len(ml_only)}   AI-only: {len(ai_only)}")

    ai_idx = index_by_prefix({k: ai_table[k] for k in ai_only})

    no_counterpart = 0
    near_misses = 0
    segment_breaks = Counter()
    examples = defaultdict(list)

    for key in ml_only:
        m = ml_table[key]["metadata"]
        candidates = ai_idx.get((m.get("company_code"), m.get("document_nr")))
        if not candidates:
            no_counterpart += 1        # doc absent from AI file entirely -- the
            continue                   # ordinary population difference, not key damage
        mine = parts_of(m)
        best_key, best_diff = None, None
        for ai_key, theirs in candidates:
            diff = [s for s, a, b in zip(SEGMENTS, mine, theirs) if a != b]
            if best_diff is None or len(diff) < len(best_diff):
                best_key, best_diff = ai_key, diff
        near_misses += 1
        for s in best_diff:
            segment_breaks[s] += 1
            if len(examples[s]) < 5:
                examples[s].append((key, best_key))

    print(f"\nML-only keys with NO same-(company,doc) row in AI at all: {no_counterpart}")
    print(f"ML-only keys with a near-miss AI counterpart:             {near_misses}")
    print("  -> these are former matches broken by the extended key.\n")

    if near_misses:
        print("segment responsible (a near-miss can differ in several):")
        for seg, n in segment_breaks.most_common():
            print(f"  {seg:<13} breaks {n:>6} near-miss pairs  ({100*n/near_misses:.0f}%)")
        print("\nexamples per segment (ML key  <->  closest AI key):")
        for seg, _ in segment_breaks.most_common():
            print(f"  [{seg}]")
            for ml_k, ai_k in examples[seg]:
                print(f"    {ml_k}")
                print(f"    {ai_k}\n")


if __name__ == "__main__":
    main()
