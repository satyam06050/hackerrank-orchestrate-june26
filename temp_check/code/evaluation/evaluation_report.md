# Evaluation & Operational Report

## Accuracy on `sample_claims.csv` (observed n=3 of 20)

Stage 4 persisted predictions for 3 of the 20 labeled sample rows. The table
reports only those real predictions; it does not present the sample evaluation
as complete.

| Field | Exact match accuracy |
|---|---:|
| evidence_standard_met | 3/3 (100.0%) |
| claim_status | 3/3 (100.0%) |
| issue_type | 1/3 (33.3%) |
| object_part | 3/3 (100.0%) |
| valid_image | 3/3 (100.0%) |
| severity | 0/3 (0.0%) |
| risk_flags (set match) | 1/3 (33.3%) |
| risk_flags (mean Jaccard) | 0.333 |
| supporting_image_ids (set match) | 3/3 (100.0%) |

Notable mismatches:

- `user_001`: expected `severity=medium`; predicted `high`.
- `user_002`: expected `issue_type=scratch`, `severity=low`, and
  `risk_flags=none`; predicted `broken_part`, `high`, and multiple risk flags.
- `user_004`: expected `issue_type=crack`, `severity=medium`, and
  `risk_flags=none`; predicted `glass_shatter`, `high`, and multiple risk
  flags.

The failures suggest tightening the prompt's distinctions among `scratch`,
`crack`, `glass_shatter`, and `broken_part`, and making severity/risk assignment
more conservative. A complete 20-row rerun is required to measure the effect.

## Repair stats

Repair counters were held in memory and were not persisted with the real Stage
4 and Stage 5 runs. Real combined repair counts therefore cannot be recovered.
Synthetic validation-harness counters are excluded.

## Stage 5 operational analysis

| Measurement | Real value |
|---|---:|
| Claims in `dataset/claims.csv` | 44 |
| Completed rows in `output.csv` | 44 |
| Images processed | 82 |
| Runtime | 1:38:37 (5,917 seconds) |
| Average elapsed time per row | 134.5 seconds |
| Measured input tokens | 123,335 |
| Measured persisted-output tokens | 7,746 |
| Mean persisted-output tokens per row | 176.05 |

Runtime is the observed interval from `output.csv` creation at 21:25:58 IST
to its final write at 23:04:35 IST on 2026-06-19. It includes API waits and
any idle time within that interval.

Input tokens were measured with Gemini's `countTokens` endpoint using all 44
real requests: the system prompt, claim conversation, history/evidence context,
image-ID parts, and all 82 images after the pipeline's 1024-pixel,
JPEG-quality-75 compression. Output tokens were measured from all 44 persisted
result JSON objects. No generic image-token estimate was used.
[Gemini token documentation](https://ai.google.dev/gemini-api/docs/tokens).

## Model and cost

The primary model is `gemini-2.5-flash`. The assumed paid-tier prices are
$0.30 per 1,000,000 text/image/video input tokens and $2.50 per 1,000,000
output tokens, including thinking tokens. Source:
[official Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing),
retrieved 2026-06-19.

### Stage 4 partial sample cost (3 rows, 5 images)

Measured counts: 8,277 input tokens and 525 persisted-output tokens.

- Input: 8,277 * $0.30 / 1,000,000 = **$0.0024831**.
- Output: 525 * $2.50 / 1,000,000 = **$0.0013125**.
- Total represented sample cost: **$0.0037956**.

### Stage 5 full test cost (44 rows, 82 images)

- Input: 123,335 * $0.30 / 1,000,000 = **$0.0370005**.
- Output: 7,746 * $2.50 / 1,000,000 = **$0.019365**.
- Total represented test cost: **$0.0563655** (about 5.6 US cents).

These calculations use measured token and image counts. The test total is a
lower bound if Gemini generated billable thinking tokens that were not retained
in the final JSON. Historical `usageMetadata`, JSON-repair calls, and Qwen
fallback usage were not persisted, so they are excluded rather than guessed.

## Calls, rate limits, and caching

- Artifacts evidence at least 3 successful Stage 4 calls and 44 successful
  Stage 5 calls. Exact retry and fallback counts were not persisted.
- Calls are sequential. Malformed JSON receives at most one additional model
  call; Gemini API failures route once to
  `qwen/qwen2.5-vl-72b-instruct`.
- The quota tier was not recorded, so no unsupported RPM/TPM number is stated.
- No batch API was needed for 44 rows. At roughly ten times this volume, batch
  processing and explicit rate-limit scheduling would be appropriate.
- No response cache was used. Atomic CSV checkpointing prevents successful
  rows from being regenerated after interruption.
