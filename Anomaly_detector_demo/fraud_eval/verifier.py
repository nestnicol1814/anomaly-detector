"""
AI-vs-base-data verdict engine (plan step 2, the reusable core).

verify() takes:
    ai_table    {transaction_id: {"ai_flags": {rule_id: bool}, ...}}   (from load_AI_table)
    base_lookup {transaction_id: {column: raw value}}                  (one base row per case)
    field_map   logical field -> {"col": base column, "type": ...}

and returns (verdict_rows, scorecard):
    verdict_rows : one dict per (case, rule) -- outcome per the plan's table
    scorecard    : one dict per rule with TP/FP/FN/TN/DATA_MISSING/UNCOMPUTABLE
                   counts + precision/recall/F1, plus NO_BASE_DATA case count

Outcomes:
    TRUE_POSITIVE / TRUE_NEGATIVE   AI agrees with the recomputed truth
    FALSE_POSITIVE                  AI flagged; base data says condition not met
    FALSE_NEGATIVE                  AI didn't flag; base data says condition met
    DATA_MISSING                    required base fields blank -> no verdict
    UNCOMPUTABLE                    rule needs data the extract can't provide
    NO_BASE_DATA                    case absent from base data (case-level, once)
"""
import pandas as pd

from .rule_specs import RULE_SPECS, FIELD_MAP

_BOOL_TRUE = {"yes", "true", "1", "y", "t", "1.0"}
_BOOL_FALSE = {"no", "false", "0", "n", "f", "0.0"}


def _typed(raw, kind):
    """Parse one raw cell to the given type. Returns (value, ok)."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None, False
    if kind == "date":
        v = pd.to_datetime(raw, errors="coerce")
        return (v, True) if not pd.isna(v) else (None, False)
    if kind == "number":
        v = pd.to_numeric(raw, errors="coerce")
        return (v, True) if not pd.isna(v) else (None, False)
    if kind == "bool":
        s = str(raw).strip().lower()
        if s in _BOOL_TRUE:
            return True, True
        if s in _BOOL_FALSE:
            return False, True
        return None, False            # blank/unknown bool = missing, not False
    s = str(raw).strip()              # string
    return (s, True) if s and s.lower() not in ("nan", "none") else (None, False)


def resolve_fields(base_row, spec, field_map):
    """Returns (values, blanks): typed values for spec.requires, and the list
    of logical fields whose base column was blank or unparseable."""
    values, blanks = {}, []
    for logical in spec.requires:
        entry = field_map[logical]
        raw = base_row.get(entry["col"])
        v, ok = _typed(raw, entry["type"])
        if ok:
            values[logical] = v
        else:
            blanks.append(logical)
    return values, blanks


def _evidence(values):
    return "; ".join(
        f"{k}={v.date() if isinstance(v, pd.Timestamp) else v}" for k, v in values.items()
    )


def verify(ai_table, base_lookup, field_map=None, rules=None):
    field_map = FIELD_MAP if field_map is None else field_map
    rules = RULE_SPECS if rules is None else rules

    verdict_rows = []
    no_base = []

    for tid, ai_entry in ai_table.items():
        base_row = base_lookup.get(tid)
        if base_row is None:
            no_base.append(tid)
            continue
        ai_flags = ai_entry["ai_flags"]

        for rid, spec in rules.items():
            ai_flag = bool(ai_flags.get(rid, False))
            if not spec.computable:
                outcome, detail = "UNCOMPUTABLE", spec.reason_uncomputable
            else:
                values, blanks = resolve_fields(base_row, spec, field_map)
                if blanks:
                    outcome, detail = "DATA_MISSING", "blank: " + ",".join(blanks)
                else:
                    met = bool(spec.predicate(values))
                    outcome = ("TRUE_POSITIVE" if met else "FALSE_POSITIVE") if ai_flag \
                        else ("FALSE_NEGATIVE" if met else "TRUE_NEGATIVE")
                    detail = _evidence(values)
            verdict_rows.append({
                "transaction_id": tid,
                "rule": rid,
                "ai_flag": ai_flag,
                "outcome": outcome,
                "evidence": detail,
            })

    return verdict_rows, _scorecard(verdict_rows, rules, no_base)


def _scorecard(verdict_rows, rules, no_base):
    counts = {rid: {"TRUE_POSITIVE": 0, "FALSE_POSITIVE": 0, "FALSE_NEGATIVE": 0,
                    "TRUE_NEGATIVE": 0, "DATA_MISSING": 0, "UNCOMPUTABLE": 0}
              for rid in rules}
    for r in verdict_rows:
        counts[r["rule"]][r["outcome"]] += 1

    rows = []
    for rid, c in counts.items():
        tp, fp, fn = c["TRUE_POSITIVE"], c["FALSE_POSITIVE"], c["FALSE_NEGATIVE"]
        precision = tp / (tp + fp) if (tp + fp) else None
        recall = tp / (tp + fn) if (tp + fn) else None
        f1 = (2 * precision * recall / (precision + recall)
              if precision is not None and recall is not None and (precision + recall)
              else None)
        rows.append({
            "rule": rid, "name": rules[rid].name,
            **c,
            "precision": round(precision, 3) if precision is not None else None,
            "recall": round(recall, 3) if recall is not None else None,
            "f1": round(f1, 3) if f1 is not None else None,
        })
    return {"per_rule": rows, "no_base_data_cases": no_base}
