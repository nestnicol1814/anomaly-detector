# AI Verification Plan — AI vs Base Data (Revision 2)

**Revision note:** Revision 1 framed verification as "ML vs AI: who was right per
disagreement." Rev 2 pivots per project direction: the AI system will eventually
replace ML, so the AI is verified **directly against the base transaction data**
(ground truth). ML is no longer required for verification — it becomes an optional
cross-reference. The ML-vs-AI comparison pipeline (`fraud_eval`, `isolate_mismatches`)
stays as-is for the agreement statistics; this plan covers correctness.

## Core idea

For every case, recompute every computable rule from raw base-data fields.
That computed flag vector IS the ground truth. Compare the AI's flag vector
against it:

| AI flag | base computation | outcome |
|---|---|---|
| triggered | condition met | `TRUE_POSITIVE` — AI correct |
| triggered | condition not met | `FALSE_POSITIVE` — AI hallucinated |
| not triggered | condition met | `FALSE_NEGATIVE` — AI missed |
| not triggered | condition not met | `TRUE_NEGATIVE` — AI correct |
| any | required base fields blank | `DATA_MISSING` (fields listed) |
| any | rule not computable from extract | `UNCOMPUTABLE` |

Consequences of this design (vs Rev 1):
- Rules must be computed on **all cases**, not only flagged ones — false negatives
  are invisible otherwise.
- The evaluation population is **every AI-export case with base-data coverage**
  (~59k), no longer capped by the 10,386 ML∩AI intersection.
- The evaluation survives ML's retirement unchanged.

## Files to build

### 1. `fraud_eval/rule_specs.py` — every rule as data

```python
@dataclass
class RuleSpec:
    rule_id: str
    name: str
    requires: list        # logical field names
    predicate: callable   # dict of typed values -> bool
    computable: bool = True
    reason_uncomputable: str = ""
```

- All rules R01–R27 encoded from the ICCC prompt's "COMPUTED FIELDS AND RULE LOGIC"
  section (R01/R02 weekday checks; R03/R04/R27 date arithmetic; R06/R07/R08 value
  thresholds; R09 name prefix; R13–R16 geography comparisons; R17 name-match ratio).
- History-dependent rules (R05 two-month lookback; R06 cumulative if the base extract
  lacks cumulative fields) declared `computable=False` with the reason — unless the
  base data turns out to contain the needed history, in which case they get predicates
  too.
- `FIELD_MAP`: logical field -> base-data column name + type (`date`/`number`/`string`/
  `bool`). **Base column names are TODO placeholders** until the real header row is
  known; `validate_mapping(df)` runs at startup and fails loudly on any missing column.
- One shared `resolve_fields(row, spec)` does all parsing/typing centrally
  (`pd.to_datetime(errors="coerce")` etc.); predicates never parse. Blank/unparseable
  required fields short-circuit to `DATA_MISSING` before the predicate runs.

### 2. `verify_ai.py` — the verdict engine

```python
BASE_PATH = r"TODO"        # base transaction dataset -- user uploads later
AI_PATH   = r"TODO"        # ADCMS export (current one)
```

1. Load AI export via `fraud_eval.loaders.load_AI_table` (flags + ids, existing code).
2. Load base data: `usecols` = only columns FIELD_MAP needs + key columns; chunked
   read if large; build `transaction_id` with `make_transaction_id` (same
   normalization as everywhere else — key columns in base are a TODO to confirm).
3. LEFT-join AI cases to base rows; count and report AI cases with no base row
   (`NO_BASE_DATA` — excluded from scoring, never silently dropped; assert row
   count unchanged, which also catches duplicate base keys multiplying rows).
4. For each case × each rule: resolve fields -> compute -> outcome per the table
   above. Plain loop or per-rule vectorization; either is fast enough.
5. Outputs:
   - `ai_verdicts.csv` — (case, rule, ai_flag, base_condition, outcome, evidence,
     blank_fields) — **only rows where outcome is FP / FN / DATA_MISSING** (TP/TN
     kept as counts only, otherwise the file is 59k × 15 rows of mostly agreement)
   - `ai_rule_scorecard.csv` — per rule: TP / FP / FN / TN / DATA_MISSING /
     UNCOMPUTABLE counts, precision, recall, F1 — **the headline deliverable: the
     AI's true per-rule accuracy against source data, independent of ML**
   - console summary sorted by FP+FN descending

### 3. Validation before trusting it

- `make_verifier_fixtures.py`: tiny synthetic base + AI files planting one known case
  per outcome class per rule family; run end-to-end, assert expected verdicts.
- Hand-check ~5 real cases per top-error rule against the scorecard (the hand-check
  the user planned anyway — now it validates the engine instead of replacing it).
- Cross-reference sanity check: rules where ML flags exist should mostly agree with
  the base computation; a rule where ML and the base computation disagree wholesale
  means the FIELD_MAP points at the wrong column (ML is not ground truth, but it is
  a good smoke alarm).

### 4. AI investigation stage (unchanged in spirit)

Clusters are now (rule × outcome × cause): all `UNCOMPUTABLE`, samples per big
FP/FN cluster, the unexplained residual. Packets rendered per `audit_agent_prompt.md`;
findings appended to `findings_log.jsonl` with the controlled `cause_category`
vocabulary; synthesizer reads the log and the scorecard, writes the aggregate report.
`DATA_MISSING` clusters are documented as data-quality findings, not sent to the AI
to "infer" — missing data cannot be inferred, only reported.

## Order of construction

1. `rule_specs.py` with FIELD_MAP TODOs  ← buildable now
2. `verify_ai.py` with BASE_PATH/AI_PATH TODOs  ← buildable now
3. `make_verifier_fixtures.py` + green fixture run  ← buildable now
4. User fills BASE_PATH, FIELD_MAP base columns, key columns  ← needs base header row
5. Real run -> scorecard -> hand-check validation
6. Investigation packets for what the scorecard can't explain

## Pending inputs from the user (do not guess these)

1. **Official rule specifications** — for each rule to be checked: which base columns
   it uses and the exact condition/threshold. These OVERRIDE the current
   `rule_specs.py` predicates, which were transcribed from the ICCC system prompt and
   carry two CONFIRM markers (R01/R02 date-field swap; R17 ratio definition). When the
   list arrives, each spec is updated to match it verbatim and the fixture test is
   extended accordingly.
2. **Rule shortlist** — the subset of rules actually worth verifying (not all rules
   were problematic). Implementation: a `RULES_TO_CHECK = [...]` list at the top of
   `verify_ai.py`; the engine already accepts a filtered rules dict
   (`verify(..., rules={r: RULE_SPECS[r] for r in RULES_TO_CHECK})`), so non-listed
   rules are simply never computed — no spec or FIELD_MAP entry needed for them,
   and validate_mapping() only enforces columns for the shortlisted rules.

Until both lists arrive, `rule_specs.py` stands as a complete draft; no further
coding on specs.

## Open questions (answered by the base file's header row)

- Base key columns for company code / document number, and grain (document vs line
  item; if line-item, collapse rule TBD).
- Whether base contains history/cumulative fields (decides if R05/R06 are computable).
- Date column formats (decides resolver parsing).
