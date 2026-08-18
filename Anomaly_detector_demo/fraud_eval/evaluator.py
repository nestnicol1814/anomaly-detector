"""
AnomalyEval: the orchestrator class (frames 1-6 of the design).

    from fraud_eval import AnomalyEval

    ev = AnomalyEval()
    results = ev.run(ai_csv="ai_rules.csv", ml_csv="ml_ground_truth.csv")
    results.to_csv("results.csv")
    ev.print_summary(results)

Loads ML rule table (comma-separated rule markers) and AI rule table (binary columns),
normalizes both to the same internal format, merges on company_code+document_nr,
and scores the agreement.

`transactions_csv=` is accepted and stored on the result but not yet used --
it's the documented extension point for the future audit agent (frames 7-10)
that will factually verify AI claims against raw transaction field values.
"""
import csv
from dataclasses import dataclass, field

from .comparison import aggregate, score_case
from .loaders import load_ml_table, load_AI_table


@dataclass
class EvalResults:
    per_case: list
    aggregate: dict
    unmatched_ids: set
    transactions: dict = field(default=None)

    def to_csv(self, path):
        if not self.per_case:
            raise ValueError("No cases to write -- per_case is empty")
        fieldnames = list(self.per_case[0].keys())
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self.per_case)


class AnomalyEval:
    """Loads ML rule table (comma-separated rule markers) + AI rule table (binary columns),
    normalizes both to the same internal format, merges on company_code+document_nr,
    and scores the agreement."""

    def run(self, ai_csv, ml_csv, transactions_csv=None):
        ml_table = load_ml_table(ml_csv)
        ai_table = load_AI_table(ai_csv)
        transactions = self._load_transactions(transactions_csv) if transactions_csv else None

        unmatched_ids = set(ai_table) ^ set(ml_table)
        matched_ids = sorted(set(ai_table) & set(ml_table))

        per_case = []
        for transaction_id in matched_ids:
            ai_data = ai_table[transaction_id]
            
            # Create parsed report structure from CSV data (no text parsing needed)
            parsed = {
                "parse_status": "ok",
                "ai_flags": ai_data["ai_flags"],
            }
            
            per_case.append(score_case(transaction_id, parsed, ml_table[transaction_id]))

        return EvalResults(
            per_case=per_case,
            aggregate=aggregate(per_case),
            unmatched_ids=unmatched_ids,
            transactions=transactions,
        )

    @staticmethod
    def _load_transactions(transactions_csv):
        """Placeholder loader for raw per-transaction field values (frame 8's
        factual-verification input). Kept intentionally simple until the
        audit agent that consumes it is built."""
        with open(transactions_csv, newline="", encoding="utf-8") as f:
            return {row["transaction_id"]: row for row in csv.DictReader(f)}

    @staticmethod
    def print_summary(results):
        if results.unmatched_ids:
            print(f"WARNING: no ground-truth/report pair for: {sorted(results.unmatched_ids)}")

        print(f"\nScored {results.aggregate['n_scored']} of {results.aggregate['n_total']} transactions\n")

        print(f"{'ID':<20}{'TP':<3}{'FP':<3}{'FN':<3}{'Prec':<6}{'Rec':<6}{'F1':<6}{'Hallucinated':<20}{'Missed':<20}")
        print("-" * 110)
        for r in results.per_case:
            txn_id = r['transaction_id'][:20]  # Truncate long IDs
            print(f"{txn_id:<20}{r['n_true_positive']:<3}{r['n_hallucinated']:<3}{r['n_missed']:<3}{r['precision']:<6}{r['recall']:<6}{r['f1']:<6}"
                  f"{r['hallucinated_rules'][:20]:<20}{r['missed_rules'][:20]:<20}")

        agg = results.aggregate
        print("\n" + "=" * 110)
        print("AGGREGATE SUMMARY")
        print("=" * 110)
        if agg["n_scored"] == 0:
            print("  No transactions to analyze.")
            return
        print(f"Avg Precision:         {agg['avg_precision']}")
        print(f"Avg Recall:            {agg['avg_recall']}")
        print(f"Avg F1:                {agg['avg_f1']}")
        print(f"Hallucination Rate:    {agg['hallucination_rate']}")
        print(f"Total Hallucinated:    {agg['total_hallucinated_rules']}")
