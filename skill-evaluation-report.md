# SKILL: evaluation-and-cost-report

## When to use
After the pipeline successfully runs on both sample_claims.csv and
claims.csv, use this skill to build `evaluation/main.py` (scoring) and
`evaluation/evaluation_report.md` (write-up).

## evaluation/main.py — required behavior
1. Run the same pipeline function used for claims.csv against
   sample_claims.csv inputs only (ignore its label columns as input).
2. For each output column that has an expected value in sample_claims.csv,
   compute exact-match accuracy:
   - evidence_standard_met, claim_status, issue_type, object_part,
     valid_image, severity: exact string/bool match
   - risk_flags: set equality (order independent) AND a softer
     partial-overlap (Jaccard) metric, report both
   - supporting_image_ids: set equality
3. Print a per-column accuracy table and dump it to
   `evaluation/sample_eval_results.csv` (predicted vs expected per row) so
   mismatches can be inspected by hand.
4. Do NOT silently pass/fail — actually print which rows mismatched and
   on which field, so the prompt can be iterated against real failures.

## evaluation_report.md — required sections (keep it short, factual, no fluff)

```markdown
# Evaluation & Operational Report

## Accuracy on sample_claims.csv (n=20)
| Field | Exact match accuracy |
|---|---|
| evidence_standard_met | X/20 |
| claim_status | X/20 |
| issue_type | X/20 |
| object_part | X/20 |
| valid_image | X/20 |
| severity | X/20 |
| risk_flags (set match) | X/20 |
| supporting_image_ids (set match) | X/20 |

Notable mismatches and how the prompt was adjusted: ...

## Repair stats (from enum-validation-and-repair step)
Count of fields that needed deterministic fallback repair, across sample
+ test runs.

## Operational analysis

- Model calls: 1 per claim row x N rows (sample: 20, test: <N from
  wc -l dataset/claims.csv>). Plus K JSON-parse retries observed.
- Images processed: sum of image counts across image_paths columns.
- Token usage (approx): state per-call input tokens = system prompt
  (~X tokens, measured) + per-image tokens (provider's documented
  image-token formula, e.g. ~XXX tokens per image at the resolution
  used) + transcript tokens (usually short, <200 tokens). Output tokens
  per call ~100-200 (small JSON object). Multiply by call count for
  total.
- Cost estimate: state the exact $/1M input and $/1M output token price
  used (name the model + pricing source/date), multiply through. Give
  one number for sample run, one for full test run.
- Latency: measured wall-clock time for the full claims.csv run (just
  time the script), plus average per-call latency.
- Rate limits: state the provider's RPM/TPM tier you're on (or assumed
  free/cheap tier), and that calls are sequential with a small fixed
  delay / exponential backoff on 429, which is sufficient at this row
  count. No batching API needed below ~500 rows; if row count were 10x+
  larger, note that the batch API would be the next step (but explicitly
  say you did not need it here).
- Caching: none needed (each row's image+text is unique); note that if
  the same image appeared in multiple test runs during development, the
  raw API responses were optionally cached to disk by row id to avoid
  re-paying for repeated dev runs (state whether you actually did this).
```

## Tone/level of rigor expected
This is meant to show you *thought about* cost/latency/rate limits, not a
perfectly tuned production system. Real measured numbers (actual run
time, actual row/image counts) are better than precise-looking guesses.
Round honestly and say "approx."