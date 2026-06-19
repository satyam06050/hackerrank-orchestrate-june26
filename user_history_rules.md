# SKILL: user-history-risk-rules

## When to use
Use when building the pure-Python `build_history_note(user_id)` step that
runs BEFORE the model call (its output becomes part of the prompt context)
and the post-call risk-flag union step (its output gets merged with the
model's visual risk flags).

## Why pure Python, not the model
`user_history.csv` is small structured numeric/categorical data per user.
There is no visual judgment required to read it. Computing the risk
signal in code is deterministic, free, and removes a place the model
could misread a number.

## Inputs (per user_id row)
`past_claim_count`, `accept_claim`, `manual_review_claim`,
`rejected_claim`, `last_90_days_claim_count`, `history_flags`,
`history_summary`

## Suggested scoring rule (tune against sample_claims.csv patterns)

```python
def history_risk(row):
    flags = set()
    rejected_rate = row.rejected_claim / max(row.past_claim_count, 1)
    if row.history_flags and row.history_flags.strip().lower() not in ("", "none"):
        flags.add("user_history_risk")
    if rejected_rate >= 0.3:
        flags.add("user_history_risk")
    if row.last_90_days_claim_count >= 3:
        flags.add("user_history_risk")
    if flags:
        flags.add("manual_review_required")
    return flags
```

Calibrate the thresholds against the labeled examples in
sample_claims.csv: e.g. a user with `history_flags=user_history_risk` and
a summary mentioning "exaggerated claims" should reliably produce
`user_history_risk;manual_review_required` in the final output, both when
the claim is `supported` (risk noted but doesn't override clear evidence)
and when it's `contradicted` (risk reinforces the contradiction
narrative).

## What goes INTO the prompt (not the raw CSV row)
Pass the model a short natural-language note, not raw columns, e.g.:

> "User history note: 3 of 7 past claims were rejected; recent activity
> (4 claims in last 90 days) is elevated; history summary: 'Several
> exaggerated vehicle damage claims in recent history.'"

This keeps the model focused on visual judgment while still giving it
qualitative context for its justification text. If the user has clean
history, the note should say so plainly: "User history note: no risk
indicators; N past claims, mostly accepted."

## What goes INTO the final output risk_flags column
Union of:
1. Visual/model-detected flags (blurry_image, claim_mismatch, wrong_angle, etc.)
2. `history_risk(row)` flags computed in Python as above

Do NOT let the model decide on its own whether to add
`user_history_risk` — it only has the summarized note, and the actual
threshold decision (rejected_rate, recent count) should be deterministic
and reproducible, not vibes-based per call.