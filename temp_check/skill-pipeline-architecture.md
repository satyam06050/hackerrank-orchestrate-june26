# SKILL: claims-pipeline-architecture

## When to use
Use this skill when implementing `code/main.py` for the Multi-Modal Evidence
Review task. It defines the required architecture and what NOT to build.

## Architecture (mandatory shape)

```
load_csvs()              # claims.csv, evidence_requirements.csv, user_history.csv
for each row in claims.csv:
    history_note   = build_history_note(user_id)        # pure python, no model call
    evidence_ctx   = lookup_evidence_requirement(claim_object, ...)  # pure python
    images         = load_images(image_paths)            # base64 encode
    raw_json       = classify_claim(row, history_note, evidence_ctx, images)  # ONE model call
    result         = validate_and_repair(raw_json, image_ids)  # pure python
    merged_flags   = union(result.risk_flags, history_note.suggested_flags)
    write_row(result, merged_flags)
write output.csv
```

## Hard rules

1. **Exactly one vision/LLM API call per claim row.** No multi-step chains,
   no self-critique second pass, no per-image separate calls. If JSON
   parsing fails, retry the SAME call at most once with a "return valid
   JSON only" reminder appended. That's the only retry allowed.
2. **No retrieval system (no BM25, no embeddings, no vector DB).**
   `evidence_requirements.csv` and `user_history.csv` are small structured
   tables — use plain pandas/dict lookups keyed by `claim_object`/`user_id`.
3. **All enum validation and repair happens in Python after the model
   call**, never by asking the model again. If a returned value isn't in
   the allowed list, snap it to `unknown` (for issue_type/object_part) or
   drop it (for risk_flags) or `not_enough_information`/`unknown` as the
   safe fallback for status/severity. Log every repair so you can report
   how often it happened in the eval report.
4. **`supporting_image_ids` must be filtered against the actual image_ids
   present in that row.** Drop any hallucinated id the model invents.
5. **Risk flags are a union of two sources**: what the model detects visually
   (e.g. blurry_image, claim_mismatch) and what you precompute from
   user_history.csv (user_history_risk, manual_review_required). Do not ask
   the model to read user_history.csv directly — pass it a short
   pre-summarized note instead, computed in Python (see
   user-history-rules skill).
6. **No agent frameworks** (no LangChain/LlamaIndex/etc). Plain Python +
   one API client call function is sufficient and preferred.
7. Process `sample_claims.csv` first, diff against its labels column by
   column, fix the prompt based on real mismatches, THEN run on
   `claims.csv` to produce final `output.csv`. Never skip the sample-eval
   step before producing final output.

## File layout expected by the harness

```
code/
  main.py                 # entry point, runs pipeline on dataset/claims.csv -> output.csv
  prompt.md                # system prompt (see prompt.md)
  evaluation/
    main.py                # runs pipeline on sample_claims.csv and scores it
    evaluation_report.md   # cost/latency/token analysis, written after real run
```

## What NOT to do
- Don't build a retrieval index.
- Don't call the model more than once per row except the single allowed
  JSON-repair retry.
- Don't let the model do CSV lookups — that's deterministic code's job.
- Don't over-engineer batching/async unless the row count is large (check
  `wc -l dataset/claims.csv` first — if it's under a few hundred rows,
  sequential calls with a small sleep/backoff is enough).