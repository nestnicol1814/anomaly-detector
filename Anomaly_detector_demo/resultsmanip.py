import pandas as pd
data2 = pd.read_csv('C:\\Users\\NGarbea\\OneDrive - NESTLE\\Documents\\Anomaly_detector_demo\\per_case_results.csv')

data2.shape

hallucinated_cases = data2[data2['n_hallucinated'] > 0]
missed_cases = data2[data2['n_missed'] > 0]

print("Cases with hallucinated rules:")
print(hallucinated_cases[['transaction_id', 'hallucinated_rules']])
print("\nCases with missed rules:")
print(missed_cases[['transaction_id', 'missed_rules']])


from fraud_eval.loaders import load_ml_table, load_AI_table
from fraud_eval.comparison import compare_rules, score_case, aggregate

# Load data
ml_table = load_ml_table("C:\\Users\\NGarbea\\OneDrive - NESTLE\\Documents\\Anomaly_detector_demo\\Report Case Extract.xlsx")
ai_table = load_AI_table("C:\\Users\\NGarbea\\OneDrive - NESTLE\\Documents\\Anomaly_detector_demo\\ADCMS Case Rules 2026 Export.xlsx")

# Check what you loaded
print(f"ML records: {len(ml_table)}")
print(f"AI records: {len(ai_table)}")

# Look at first record structure
first_id = list(ml_table.keys())[0]
print(f"ML first record: {ml_table[first_id]}")
print(f"AI first record: {ai_table[first_id]}")