import warnings

import pandas as pd

warnings.filterwarnings('ignore')

from fraud_eval import AnomalyEval

# Paths live in my_paths.py (gitignored) so pulls/resets never wipe them.
# First time: copy my_paths_example.py -> my_paths.py and put your paths there.
try:
    from my_paths import ML_CSV, AI_CSV, RESULTS_CSV
except ImportError:
    raise SystemExit(
        "my_paths.py not found. Copy my_paths_example.py to my_paths.py "
        "(same folder) and set your file paths there -- one-time setup."
    )

ev = AnomalyEval()
results = ev.run(ai_csv=AI_CSV, ml_csv=ML_CSV)

per_case_df = pd.DataFrame(results.per_case)
ev.print_summary(results)
per_case_df.to_csv(RESULTS_CSV, index=False)
print(f"\nwrote {len(per_case_df)} rows to {RESULTS_CSV}")
