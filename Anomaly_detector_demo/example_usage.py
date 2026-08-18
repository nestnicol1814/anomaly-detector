"""
Example of importing and running the fraud_eval module against a dataset.
Copy this pattern into a new script when pointing it at a different
(ML table, AI reports) pair -- nothing inside fraud_eval/ needs to change.
"""
from fraud_eval import FraudEval

ev = FraudEval()
results = ev.run(reports_dir="reports", ml_csv="ml_ground_truth.csv")

ev.print_summary(results)
results.to_csv("results.csv")
