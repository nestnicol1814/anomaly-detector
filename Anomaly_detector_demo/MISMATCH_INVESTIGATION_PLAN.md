# Mismatch Investigation Plan

Goal: for every (case, rule) disagreement between ML and AI, determine **who was right** by
recomputing the rule from source data, then have an AI agent explain **why** the wrong side
got it wrong — per-rule, at an aggregate level, with case-level evidence attached.

Inputs that already exist:

| artifact | produced by | grain |
|---|---|---|
| `per_case_results.csv` | `test.py` | one row per matched case (10,386) |
| `hallucinated_rules.csv` | `isolate_mismatches.py` | one row per (case, rule) the AI claimed and ML didn't |
| `missed_rules.csv` | `isolate_mismatches.py` | one row per (case, rule) ML flagged and the AI didn't |
| per-rule frequency counts | `isolate_mismatches.py` console output | rule × direction |
| Report Case Extract.xlsx (ML) | ML system export | raw ML rows incl. [Entry Date], [Supplier Nr], [G/L Account], ... |
| ADCMS Case Rules 2026 Export.xlsx (AI) | AI system export | raw AI rows incl. SUPPLIER_COUNTRY, ENTRY_DATE, POSTING_DATE, ... |

---

## Step 1 — Build the trouble-case working table (`build_trouble_table.py`)

1. Stack `hallucinated_rules.csv` (+ column `direction="hallucinated"`) and
   `missed_rules.csv` (+ `direction="missed"`) into ONE table at **(case, rule, direction)**
   grain (~2,100 rows). Keep this grain all the way through — do not collapse to case level.
2. Inner-join the raw source columns onto it by `transaction_id`:
   - from the **AI export**: prefix columns `ai_` (this file carries most raw fields:
     SUPPLIER_COUNTRY, ENTRY_DATE, POSTING_DATE, DOCUMENT_TYPE, SUPPLIER_NR, ...)
   - from the **ML export**: prefix columns `ml_` ([Entry Date], [Supplier Nr],
     [G/L Account], [Document Date], [Value Custom], ...)
   - **[REC-1] Join BOTH files, not one "main database".** Each export carries fields the
     other lacks; the verifier needs the union. Prefixes prevent column collisions and
     make it explicit which system supplied each value.
   - **[REC-2] Build the join key with `fraud_eval.loaders.make_transaction_id`** (same
     normalization: company code + zero-stripped doc nr). Rebuilding the key ad hoc in
     pandas is exactly how rows silently vanished before. After the join, assert
     row count is unchanged and report any (case, rule) rows that failed to find
     source data — those become verdict `SOURCE_ROW_MISSING`, not silent drops.
3. Output: `trouble_cases_enriched.csv` — one row per (case, rule, direction) with all
   `ai_*` / `ml_*` raw fields attached.

## Step 2 — Rule specification registry (`fraud_eval/rule_specs.py`)

One spec per rule, encoded as data + a small compute function, mirroring the ICCC
system prompt's "COMPUTED FIELDS AND RULE LOGIC" section:

```python
RULE_SPECS = {
  "R03": {
    "name": "Less than 30 days between vendor creation and Non-PO",
    "requires": ["entry_date", "vendor_create_date"],
    "compute": lambda f: (f["entry_date"] - f["vendor_create_date"]).days < 30,
    "computable": True,
  },
  "R05": { "name": "...", "computable": False,   # needs 2-month history not in extracts
           "reason_uncomputable": "requires prior Non-PO lookback" },
  ...
}
```

- **[REC-3] The real work in this step is the FIELD MAPPING, not the formulas.** Specs
  reference logical fields (`entry_date`); the exports have their own names
  (`ai_ENTRY_DATE`, `ml_[Entry Date]`). Maintain one explicit mapping dict
  `LOGICAL_FIELD -> [preferred column, fallback column]`, validated at startup
  (fail loudly if a mapped column doesn't exist). When ML and AI disagree on the
  same logical field's value, record BOTH — that discrepancy is itself a finding.
- **[REC-4] Classify every rule upfront** as `computable` / `uncomputable`
  (R05 two-month lookback, R06 cumulative ≥500K unless the extract has cumulative
  fields) so nobody expects verdicts the data cannot support. The uncomputable
  list goes straight to the AI investigation queue.

## Step 3 — Deterministic verifier (`verify_rules.py`) — NO LLM

For each row of `trouble_cases_enriched.csv`:

1. Look up the rule spec. If `computable == False` → verdict `UNCOMPUTABLE`.
2. Resolve required fields via the mapping. Any missing/blank → verdict `DATA_MISSING`,
   recording which fields were blank (this is a root cause, not a failure of the script).
3. Otherwise compute the condition and combine with `direction`:

| direction | condition met? | verdict |
|---|---|---|
| missed (ML yes, AI no) | yes | `ML_CORRECT` — AI truly missed it |
| missed | no | `AI_CORRECT` — ML flag was wrong/stale |
| hallucinated (AI yes, ML no) | yes | `AI_CORRECT` — AI found a real trigger ML lacked |
| hallucinated | no | `ML_CORRECT` — AI hallucinated |

4. Outputs:
   - `verdicts.csv` — (case, rule, direction, verdict, computed_value, fields_used,
     blank_fields) — the full audit trail
   - `verdict_summary.csv` — cross-tab rule × direction × verdict with counts —
     **this table alone is the first aggregate deliverable** ("R14 misses: 92%
     DATA_MISSING on bank_zone") and decides how much AI investigation is even needed.

## Step 4 — AI investigation (Copilot agent, `audit_agent_prompt.md`)

Only for what Step 3 cannot close:

- all `UNCOMPUTABLE` rows,
- a **sample (~10) per (rule × direction × verdict) cluster** to establish the *cause*
  narrative for the cluster,
- the unexplained residual (verdicts that don't cluster).

Mechanics:
1. `make_packets.py` renders each selected row into the JSON input packet defined in
   `audit_agent_prompt.md` (comparison stats + both systems' positions + raw fields +
   rule definition). One JSONL file = the investigation queue, ordered biggest
   cluster first.
2. The Copilot agent (system prompt = `audit_agent_prompt.md`) processes packets and
   its mandatory Part-2 JSON output is appended to `findings_log.jsonl` — one record
   per investigation:
   `{transaction_id, rule, direction, stage1_verdict, cause_category, cause_detail,
     evidence[], confidence}`
- **[REC-5] `cause_category` must be a controlled vocabulary** (`missing_field`,
  `wrong_field_used`, `threshold_misread`, `stale_master_data`, `timing_difference`,
  `ml_flag_error`, `unexplained`) — free text cannot be counted, categories can.
- **[REC-6] The log is append-only.** Stateless agent + stateful log gives
  resumability (skip already-investigated pairs on restart) and an audit trail the
  synthesizer may read but never edit.
- **[REC-7] ONE investigator agent, direction as a field** — not separate
  hallucination/miss agents. Same procedure both directions; two prompts would drift
  and split findings for cases appearing in both lists.

## Step 5 — Synthesis (aggregate report)

1. Pure-code aggregation first: `findings_log` + `verdict_summary` groupbys →
   per-rule cause distribution with counts and example case ids.
2. Synthesizer agent (or a single prompted run) turns that into the narrative report:
   pattern-level findings ("R14 misses are systematic: AI input lacks bank_zone —
   552/600 cases, verified on 10 samples"), each claim citing counted records.
   The synthesizer reads the log; it never writes it.

## Order of construction

1. `fraud_eval/rule_specs.py` (specs + field mapping) — gates everything
2. `build_trouble_table.py` → `trouble_cases_enriched.csv`
3. `verify_rules.py` → `verdicts.csv`, `verdict_summary.csv`  ← **stop and read this
   before building any Copilot flow; it may already answer most of the "why"**
4. `make_packets.py` → investigation queue JSONL
5. Copilot investigator + `findings_log.jsonl`
6. Synthesis report

## Verification

- Step 1: assert (case,rule,direction) row count unchanged after join; zero silent drops.
- Step 2: startup validation that every mapped column exists in the enriched table.
- Step 3: hand-check ~5 verdicts per rule against the raw Excel rows before trusting
  the cross-tab.
- Step 4: spot-check that every `findings_log` record's `evidence` fields exist in the
  packet it was given (no invented fields).
