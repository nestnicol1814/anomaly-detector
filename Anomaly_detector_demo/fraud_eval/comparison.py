"""
Rule-set comparison and aggregate statistics (frame 6 of the design).

All pure code -- set comparisons and arithmetic, no LLM involved.
"""
from .rules import RULE_FLAGS


def compare_rules(ai_flags, ml_flags):
    """Compare two {rule_id: bool} dicts over the full known rule catalogue."""
    all_ids = set(RULE_FLAGS)
    tp, fp, fn, tn = [], [], [], []
    for rid in sorted(all_ids):
        ai = ai_flags.get(rid, False)
        ml = ml_flags.get(rid, False)
        if ai and ml:
            tp.append(rid)
        elif ai and not ml:
            fp.append(rid)
        elif not ai and ml:
            fn.append(rid)
        else:
            tn.append(rid)
    precision = len(tp) / (len(tp) + len(fp)) if (tp or fp) else 1.0
    recall = len(tp) / (len(tp) + len(fn)) if (tp or fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "true_positive": tp,
        "hallucinated_by_ai": fp,   # AI says triggered, ML says not
        "missed_by_ai": fn,         # ML triggered, AI didn't flag
        "true_negative": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def score_case(transaction_id, parsed_report, ml_entry):
    """Build the per-transaction result row. Compares AI and ML rule flags."""
    rules = compare_rules(parsed_report["ai_flags"], ml_entry["ml_flags"])
    return {
        "transaction_id": transaction_id,
        "parse_status": "ok",
        "precision": round(rules["precision"], 2),
        "recall": round(rules["recall"], 2),
        "f1": round(rules["f1"], 2),
        "hallucinated_rules": ",".join(rules["hallucinated_by_ai"]) or "-",
        "missed_rules": ",".join(rules["missed_by_ai"]) or "-",
        "n_true_positive": len(rules["true_positive"]),
        "n_hallucinated": len(rules["hallucinated_by_ai"]),
        "n_missed": len(rules["missed_by_ai"]),
    }


def aggregate(per_case):
    """Averages computed over all cases.

    hallucination_rate = total hallucinated rule claims / total rules the AI
    claimed were triggered (true positives + hallucinated). This is the
    headline "how often does the AI's rule claims differ from the ML model" metric,
    distinct from precision (which is per-case then averaged).
    """
    n = len(per_case)

    if not per_case:
        return {
            "n_total": 0,
            "n_scored": 0,
            "avg_precision": None,
            "avg_recall": None,
            "avg_f1": None,
            "total_hallucinated_rules": 0,
            "hallucination_rate": None,
        }

    avg_precision = sum(r["precision"] for r in per_case) / n
    avg_recall = sum(r["recall"] for r in per_case) / n
    avg_f1 = sum(r["f1"] for r in per_case) / n

    total_true_positive = sum(r["n_true_positive"] for r in per_case)
    total_hallucinated = sum(r["n_hallucinated"] for r in per_case)
    total_ai_claimed_triggered = total_true_positive + total_hallucinated
    hallucination_rate = (
        total_hallucinated / total_ai_claimed_triggered
        if total_ai_claimed_triggered
        else 0.0
    )

    return {
        "n_total": n,
        "n_scored": n,
        "avg_precision": round(avg_precision, 2),
        "avg_recall": round(avg_recall, 2),
        "avg_f1": round(avg_f1, 2),
        "total_hallucinated_rules": total_hallucinated,
        "hallucination_rate": round(hallucination_rate, 2),
    }
