import sys
import os
import pandas as pd
import warnings
from io import StringIO

# Suppress ALL output
pd.set_option('display.max_rows', 0)
pd.set_option('display.max_columns', 0)
warnings.filterwarnings('ignore')

from fraud_eval import AnomalyEval


# Run silently
ev = AnomalyEval()
results = ev.run(
    ai_csv="C:\\Users\\NGarbea\\OneDrive - NESTLE\\Documents\\Anomaly_detector_demo\\ADCMS Case Rules 2026 Export.xlsx",
    ml_csv="C:\\Users\\NGarbea\\OneDrive - NESTLE\\Documents\\Anomaly_detector_demo\\Report Case Extract.xlsx"
)
data2 = pd.DataFrame(results.per_case)
per_case_df = pd.DataFrame(results.per_case)
print(per_case_df)  # All columns: transaction_id, precision, recall, f1, TP, FP, FN, etc.

print(f"\nAvg Precision: {results.aggregate['avg_precision']}")
print(f"Avg Recall: {results.aggregate['avg_recall']}")
print(f"Avg F1: {results.aggregate['avg_f1']}")
print(f"Total Hallucinated: {results.aggregate['total_hallucinated_rules']}")

print(data2.head())  # Show first few rows of the per-case results
data2.to_csv("C:\\Users\\NGarbea\\OneDrive - NESTLE\\Documents\\Anomaly_detector_demo\\per_case_results.csv", index=False)