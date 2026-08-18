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

# Load data -- loaders now return (table, report). The report is the row accounting.
ml_table, ml_report = load_ml_table("C:\\Users\\NGarbea\\OneDrive - NESTLE\\Documents\\Anomaly_detector_demo\\Report Case Extract.xlsx")
ai_table, ai_report = load_AI_table("C:\\Users\\NGarbea\\OneDrive - NESTLE\\Documents\\Anomaly_detector_demo\\ADCMS Case Rules 2026 Export.xlsx")

# Where the rows went (raw -> blank-key dropped -> duplicates collapsed -> kept)
print(ml_report.summary())
print(ai_report.summary())
print(f"ML unique transactions: {len(ml_table)}   AI unique transactions: {len(ai_table)}")
print(f"matched on merge: {len(set(ml_table) & set(ai_table))}")

# Look at first record structure
first_id = list(ml_table.keys())[0]
print(f"ML first record: {ml_table[first_id]}")
print(f"AI first record: {ai_table[first_id]}")